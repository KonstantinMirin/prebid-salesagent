"""Guard: idempotency is implemented ONCE, and every tool that needs it joins that one seam.

AdCP 3.1.1 (``dist/compliance/3.1.1/universal/idempotency.yaml``) states one
contract for every mutating task — "Every mutating request in AdCP carries an
idempotency_key so buyers can safely retry after network errors without
double-booking" — with five observable behaviors (fresh key executes; replay
returns the cached response without re-executing; same key + different payload
-> IDEMPOTENCY_CONFLICT; a different key is a new request; errors never cache).
One contract admits exactly one implementation.

``create_media_buy`` already implements it: ``IdempotencyAttemptRepository``,
``DEFAULT_REPLAY_TTL``, ``canonical_payload_hash`` / ``canonical_request_hash``,
``AdCPIdempotencyConflictError`` / ``AdCPIdempotencyExpiredError``, TTL expiry and
race resolution. The failure mode this guard exists to prevent is the obvious one:
the next tool that needs replay protection grows its OWN cache lookup, its own
conflict check, and its own TTL rule — two implementations of one contract, which
then drift. That is a correctness defect under CLAUDE.md's DRY invariant, not a
style preference.

Two arms:

* **SINGLE** — the verbatim-cache repository is reached from exactly ONE
  non-infrastructure production module. Joining the seam therefore has to mean
  reusing it (importing the shared helpers), never copying it. This arm is green
  today and ratchets: it reddens the moment a second module grows its own lookup.
* **JOINED** — every tool whose PINNED request schema marks ``idempotency_key``
  REQUIRED must reach that seam from its own implementation. Derived from the
  pinned schema, not from a hand-written tool list, so a future tool that gains a
  required ``idempotency_key`` is graded automatically.

Both arms are derived. Nothing here is a literal list of tool names except
``_SEAM_JOIN_PENDING``, which is a shrink-only ledger of tools not yet migrated.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.version_compat import pinned_request_schema_fields
from tests.unit._architecture_helpers import assert_violations_match_allowlist

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Every production use of the verbatim success cache goes through the unit of
# work's ``idempotency_attempts`` repository handle. Anchoring on the attribute
# name (rather than on method names like ``record_success``, which other services
# also define) matches the seam and nothing else.
SEAM_ANCHOR = "idempotency_attempts"

# Infrastructure that DEFINES the seam rather than using it: the repository and
# the unit of work that exposes it.
INFRASTRUCTURE = "src/core/database/repositories"

# The shared tools directory itself is not a per-tool package: a module sitting
# directly in it (media_buy_create.py) is its own implementation unit, while a
# module inside a tool sub-package (creatives/_sync.py) may place the seam
# integration in any sibling of that sub-package.
TOOLS_DIR = "src/core/tools"

# Tools whose pinned schema requires idempotency_key but which have NOT been
# migrated onto the shared seam yet. This set may only SHRINK — adding a name
# here means shipping a second silent-retry hole, which is the defect the guard
# exists to catch. All three entries are outside the current lane's scope (the
# lane named in the frozen plan covers sync_creatives); they are recorded here so
# the guard grades what the lane owns without pretending the rest are done. That
# the derived scan found THREE additional tools with the same hole — not the one
# the plan named — is itself the finding: the drop is systemic, not local.
_SEAM_JOIN_PENDING = {
    ("update_media_buy", "src/core/tools/media_buy_update.py"),
    ("sync_accounts", "src/core/tools/accounts.py"),
    ("activate_signal", "src/core/tools/signals.py"),
}


def _production_modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return None


def _touches_seam(tree: ast.Module) -> bool:
    """True when the module reads or writes the verbatim idempotency cache."""
    return any(isinstance(node, ast.Attribute) and node.attr == SEAM_ANCHOR for node in ast.walk(tree))


def _seam_modules() -> list[str]:
    """Non-infrastructure production modules that touch the idempotency cache."""
    modules = []
    for path in _production_modules():
        rel = _rel(path)
        if rel.startswith(INFRASTRUCTURE):
            continue
        tree = _parse(path)
        if tree is not None and _touches_seam(tree):
            modules.append(rel)
    return modules


def _impl_modules() -> dict[str, str]:
    """Map ``tool_name -> module path`` by locating each ``_<tool>_impl`` definition."""
    found: dict[str, str] = {}
    for path in _production_modules():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_") and node.name.endswith("_impl"):
                found[node.name[1:-5]] = _rel(path)
    return found


def _tools_requiring_idempotency_key() -> set[str]:
    """Tools whose PINNED request schema marks ``idempotency_key`` as required.

    Derived from the pin, so a schema bump that adds the requirement to another
    tool starts grading it without editing this file. Names that are not tools
    resolve to an empty required-set and drop out.
    """
    return {tool for tool in _impl_modules() if "idempotency_key" in pinned_request_schema_fields(tool)[1]}


def _implementation_unit(impl_module: str) -> list[str]:
    """The module(s) allowed to hold a tool's seam integration.

    A tool implemented directly under ``src/core/tools`` owns only its own file;
    a tool implemented inside a sub-package owns every module in that package, so
    the integration may live in ``_idempotency.py`` next to ``_sync.py`` rather
    than being forced into the orchestrator.
    """
    path = ROOT / impl_module
    if _rel(path.parent) == TOOLS_DIR:
        return [impl_module]
    return sorted(_rel(p) for p in path.parent.glob("*.py") if "__pycache__" not in p.parts)


def _dotted(module_path: str) -> str:
    return module_path[: -len(".py")].replace("/", ".")


def _detached_tools() -> set[tuple[str, str]]:
    """``(tool, impl module)`` for every required-key tool that does NOT reach the seam."""
    seam_modules = _seam_modules()
    impl_modules = _impl_modules()
    return {
        (tool, impl_modules[tool])
        for tool in _tools_requiring_idempotency_key()
        if not _reaches_seam(_implementation_unit(impl_modules[tool]), seam_modules)
    }


def _reaches_seam(module_paths: list[str], seam_modules: list[str]) -> bool:
    """True when any module in the unit is the seam or imports from it."""
    seam_dotted = {_dotted(m) for m in seam_modules}
    for module_path in module_paths:
        if module_path in seam_modules:
            return True
        tree = _parse(ROOT / module_path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in seam_dotted:
                return True
            if isinstance(node, ast.Import) and any(alias.name in seam_dotted for alias in node.names):
                return True
    return False


class TestIdempotencyIsImplementedOnce:
    """The verbatim cache has exactly one production implementation."""

    @pytest.mark.arch_guard
    def test_single_seam_module(self):
        """Exactly one non-infrastructure module reaches the idempotency cache.

        A second one means a second implementation of the replay/conflict/TTL
        rules — the drift this guard exists to prevent. Joining the seam must be
        done by importing the shared helpers, not by copying them.
        """
        seam_modules = _seam_modules()
        assert len(seam_modules) == 1, (
            "The idempotency verbatim cache must be reached from exactly ONE production "
            f"module (the shared seam); found {len(seam_modules)}: {seam_modules}. "
            "Extract the shared helpers instead of growing a second implementation."
        )


class TestEveryIdempotentToolJoinsTheSeam:
    """Every tool whose pinned schema REQUIRES idempotency_key reaches that seam."""

    @pytest.mark.arch_guard
    def test_required_key_tools_reach_the_seam(self):
        """A schema-required idempotency_key must be honored, not dropped.

        A tool that accepts ``idempotency_key`` and never consults the cache
        silently re-executes a retried write — the buyer's retry double-books.

        Graded as an exact allowlist match, so the ledger cannot rot in either
        direction: a NEW detached tool fails immediately, and a pending tool that
        has since joined the seam fails as a stale entry until it is removed.
        """
        assert _tools_requiring_idempotency_key(), (
            "non-vacuity: no tool's pinned request schema requires idempotency_key — "
            "the pinned-schema lookup is broken, so this guard would grade nothing"
        )
        assert_violations_match_allowlist(
            _detached_tools(),
            _SEAM_JOIN_PENDING,
            fix_hint=(
                "A tool listed here requires idempotency_key in the pinned request schema but "
                f"its implementation never reaches the shared idempotency seam ({_seam_modules()}), "
                "so a retried write silently re-executes. Join the existing seam — import the "
                "shared helpers; do NOT grow a second implementation."
            ),
        )
