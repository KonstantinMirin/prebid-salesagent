"""Executable-exemption meta-test for the test-credential-header ast-grep ban.

The ENFORCEMENT is an ast-grep rule, not this module. The rule lives at
``.ast-grep/rules/test-credential-header-single-producer.yml`` (discovered
through ``sgconfig.yml``'s ``ruleDirs``) and runs as its own ``make quality-ci``
line, the way ``ruff-egress.toml`` already does. It refuses a credential header
(``Authorization`` / ``x-adcp-auth``, any casing) assembled inline anywhere in
``tests/`` instead of through the one shared test-credential producer in
``tests/harness/client.py`` — the DRY defect measured on run innet_100926_1008,
where a one-line header change cost eleven edits and 691 of 1013 failures
carried AUTH_MISSING (salesagent-2l6ii).

This module stands to that rule exactly as ``tests/unit/test_ruff_egress_bans.py``
stands to ``ruff-egress.toml``: it proves the ban FIRES and that every exemption
is live rather than prose. It deliberately does NOT re-implement the detection —
an AST scan written here would be a second, divergent copy of the rule, which is
the disease this ticket is about. Every case below shells out to the real
ast-grep with the real rule file.

Six cases:

(a) POSITIVE — every credential shape that occurs in this tree matches:
    single-pair dict, multi-key dict in BOTH key orders, the lowercase
    ``authorization`` spelling, subscript assignment, and the ``x-adcp-auth``
    alias. The multi-key orders are not padding: the naive
    ``pattern: '{"Authorization": $V}'`` matches a SINGLE-PAIR dictionary only,
    and multi-key is the common shape here because these sites also set
    ``x-adcp-tenant`` and ``x-dry-run``. Measured on the live tree, that
    literal form found 27 test-side sites where the relational rule finds 57.
(b) BUILD-FAILING — a known-bad file makes the scan exit non-zero. Without
    ``severity: error`` ast-grep prints its matches and exits 0: a rule that
    reports and passes is the dormancy this ticket exists to remove.
(c) NEGATIVE — a ``Content-Type``-only dict is not flagged, and the scan exits
    0. That exit code is also the rule file's own load proof: ast-grep exits 6,
    not 0, when ``--rule`` names a file it cannot read, so a missing or
    unparseable rule fails HERE rather than passing vacuously on empty output.
(d) PATH SCOPING — the same known-bad source under ``src/`` is NOT flagged.
    The rule's ``files: ["tests/**/*.py"]`` keeps the two legitimate PRODUCTION
    producers (``src/core/property_list_resolver.py``,
    ``src/core/security/webhook_egress.py``) out BY CONSTRUCTION. That is the
    difference between an allowlist that shrinks and one that starts with a
    third of its own matches in it.
(e) REACHABLE — the rule is found by ``--filter`` under the repo's own
    ``sgconfig.yml``, i.e. it is committed into a discovered ``ruleDirs`` entry
    and not merely readable at some path this test happens to name.
(f) LIVE TREE + CLOSED EXEMPTION SET — the rule is clean over ``tests/``, the
    set of files carrying an ``# ast-grep-ignore`` for this rule equals
    ``_RECORDED_EXEMPTIONS``, and each recorded exemption is a REAL violation
    once its suppression comment is removed. A new exemption fails until it is
    recorded here; a stale one fails because it no longer violates. ast-grep
    0.41 has no unused-suppression report, so without (f) a stale exemption is
    invisible.

Case (f) is also why this module exists at all rather than the Makefile line
alone: ``test_architecture_ratchet_enforcement.py`` already rules ``ci-step``
an insufficient enforcement point in this repo (``make quality`` is a step
"nothing requires"), so the trigger is duplicated into the suite that always
runs. ast-grep stays the only detector.

Note a deliberate consequence of the verified rule: it has no
comparison-operand exclusion, so an ``assert headers == {"Authorization": ...}``
assertion IS flagged. Those sites are exemptions with a reason, not rule changes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.unit._architecture_helpers import repo_root

# The rule's id, and the path it is committed at. Both are pinned so that a
# rule filed under another name fails with a path in the message rather than a
# silently empty scan.
RULE_ID = "test-credential-header-single-producer"
RULE_FILE = f".ast-grep/rules/{RULE_ID}.yml"

# Synthetic probes are written INTO the scanned tree, because ast-grep scan has
# no `--stdin-filename`: the rule's `files:` glob can only be graded by a real
# path. The stem is excluded from the live-tree scan so a probe from a parallel
# xdist worker cannot make case (f) fail.
_PROBE_STEM = "_synthetic_credential_probe"
_PROBE_EXCLUDE_GLOB = f"!**/{_PROBE_STEM}_*.py"

# Files allowed to build a credential header inline, each carrying
# `# ast-grep-ignore: test-credential-header-single-producer` with its reason on
# the PRECEDING line (see TestExemptionForm for why the line matters). The two
# legitimate categories are outbound seller->buyer webhook/vendor credentials
# (owned by adcp.webhook_auth) and tests where the header IS the subject under
# test. Repo-root-relative paths. This set may SHRINK, never grow silently.
#
# It starts empty on purpose: the 29-row disposition table in salesagent-2l6ii
# was built with the under-catching literal rule and must be REGENERATED from
# the relational rule before any row is called an exemption.
_RECORDED_EXEMPTIONS: frozenset[str] = frozenset()


# Every credential shape observed in this tree. `label -> source`.
_CREDENTIAL_SHAPES: tuple[tuple[str, str], ...] = (
    (
        "single-pair-dict",
        'def build(token):\n    return {"Authorization": f"Bearer {token}"}\n',
    ),
    (
        "multi-key-dict-credential-first",
        'def build(token):\n    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}\n',
    ),
    (
        "multi-key-dict-credential-second",
        'def build(token):\n    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}\n',
    ),
    (
        "lowercase-spelling",
        'def build(token):\n    return {"authorization": f"Bearer {token}"}\n',
    ),
    (
        "subscript-assignment",
        'def build(headers, token):\n    headers["Authorization"] = f"Bearer {token}"\n',
    ),
    (
        "x-adcp-auth-alias",
        'def build(headers, token):\n    headers["x-adcp-auth"] = token\n',
    ),
)

_KNOWN_BAD = _CREDENTIAL_SHAPES[0][1]
_CLEAN = 'def build():\n    return {"Content-Type": "application/json"}\n'


def _ast_grep_bin() -> Path:
    """The venv-local ast-grep — exactly what ``uv run ast-grep`` resolves to.

    Resolved next to ``sys.executable`` and NOWHERE ELSE, on purpose. A PATH
    lookup would find the homebrew binary that is the only copy on this machine
    today, so this module would pass locally while the ``quality-ci`` line it
    grades failed in CI with command-not-found — the review finding this
    resolution exists to close.

    Absence FAILS, it does not skip. ast-grep is declared nowhere in
    pyproject.toml, and a skip here is the same silent nothing-graded outcome as
    a ``quality-ci`` line arranged to tolerate the binary's absence. The fix is
    to declare ``ast-grep-cli`` in the dev group, which is part of the work this
    module grades.
    """
    candidate = Path(sys.executable).parent / "ast-grep"
    assert candidate.exists(), (
        f"{candidate} does not exist: ast-grep is not installed in this environment's venv.\n"
        "Declare `ast-grep-cli` in the pyproject dev group so `uv run ast-grep` resolves — "
        "the homebrew binary on PATH is deliberately NOT used here, because relying on it "
        "would let this test pass while the make quality-ci line fails in CI."
    )
    return candidate


def _scan(
    *paths: str, rule_args: tuple[str, ...] = ("--rule", RULE_FILE), globs: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Run the real ast-grep over *paths* from the repo root.

    The single helper every case goes through (DRY): same binary, same rule
    file, same output format — so a passing case proves the REAL gate line
    would behave this way, not a lookalike.
    """
    cmd = [str(_ast_grep_bin()), "scan", *rule_args, *paths, "--json=compact"]
    for glob in globs:
        cmd += ["--globs", glob]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )


def _matches(proc: subprocess.CompletedProcess[str]) -> list[dict]:
    """Parse ast-grep's compact JSON, failing loudly on anything else.

    The returncode check is the anti-vacuity gate for every case below. ast-grep
    exits 6 when ``--rule`` names a file it cannot read and 3 when ``--filter``
    resolves no rule, printing NOTHING on stdout either way — so an absent rule
    parses as "no matches" and every negative-shaped assertion would pass while
    grading nothing at all. Only 0 (clean) and 1 (violations found) mean the
    rule actually ran.
    """
    assert proc.returncode in (0, 1), (
        f"ast-grep did not run the rule (rc={proc.returncode}). Expected 0 (clean) or 1 "
        f"(violations); anything else means {RULE_FILE} is missing, unparseable, or not "
        f"discoverable — in which case an empty match list proves nothing.\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(
            f"ast-grep did not emit JSON (rc={proc.returncode}); is {RULE_FILE} present and valid?\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        ) from exc


@contextmanager
def _probe(rel_dir: str, source: str) -> Iterator[str]:
    """Write *source* at a unique path under *rel_dir* and yield it, then remove it."""
    rel_path = f"{rel_dir}/{_PROBE_STEM}_{uuid.uuid4().hex}.py"
    path = repo_root() / rel_path
    path.write_text(source)
    try:
        yield rel_path
    finally:
        path.unlink(missing_ok=True)


def _sites(matches: list[dict]) -> list[str]:
    return sorted(f"{m['file']}:{m['range']['start']['line'] + 1}" for m in matches)


class TestBanFiresOnEveryCredentialShape:
    """(a) Every credential shape in this tree matches the rule."""

    @pytest.mark.parametrize(
        ("label", "source"),
        _CREDENTIAL_SHAPES,
        ids=[label for label, _ in _CREDENTIAL_SHAPES],
    )
    def test_credential_shape_is_flagged(self, label: str, source: str) -> None:
        with _probe("tests/unit", source) as rel_path:
            proc = _scan(rel_path)
            matches = _matches(proc)
        assert matches, (
            f"[{label}] {RULE_ID} did not flag:\n{source}\n"
            f"--- rc={proc.returncode} stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
        assert {m["ruleId"] for m in matches} == {RULE_ID}, (
            f"[{label}] flagged by another rule, not {RULE_ID}: {[m['ruleId'] for m in matches]}"
        )


class TestBanFailsTheBuild:
    """(b) `severity: error` — a match is a non-zero exit, not a printed note."""

    def test_known_bad_file_exits_non_zero(self) -> None:
        with _probe("tests/unit", _KNOWN_BAD) as rel_path:
            proc = _scan(rel_path)
        assert proc.returncode == 1, (
            f"expected exit 1 from a known-bad file, got {proc.returncode}. Without "
            f"`severity: error` ast-grep prints its matches and exits 0, so the rule "
            f"could never fail make quality-ci.\n--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )


class TestCleanCodePasses:
    """(c) A non-credential header is not flagged — and the rule file loads."""

    def test_clean_snippet_is_not_flagged(self) -> None:
        with _probe("tests/unit", _CLEAN) as rel_path:
            proc = _scan(rel_path)
            matches = _matches(proc)
        # rc == 0 is the load proof: ast-grep exits 6 when --rule names a file
        # it cannot read, so a missing/broken rule fails here, not vacuously.
        assert proc.returncode == 0, (
            f"ast-grep did not run cleanly over a clean file (is {RULE_FILE} missing or "
            f"unparseable? rc={proc.returncode}).\n--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
        assert matches == [], f"a Content-Type-only header dict was flagged: {_sites(matches)}"


class TestBanIsScopedToTests:
    """(d) `files: ["tests/**/*.py"]` — production is out of scope by construction."""

    def test_identical_source_under_src_is_not_flagged(self) -> None:
        with _probe("src/core", _KNOWN_BAD) as rel_path:
            proc = _scan(rel_path)
            matches = _matches(proc)
        assert matches == [] and proc.returncode == 0, (
            "the rule flagged a file under src/. Production owns two legitimate outbound "
            "credential producers (property_list_resolver.py, security/webhook_egress.py); "
            "they must be excluded by the rule's `files:` glob, never by allowlist entries.\n"
            f"rc={proc.returncode} sites={_sites(matches)}"
        )


class TestBanIsReachableThroughProjectConfig:
    """(e) The rule is committed under a `ruleDirs` entry sgconfig.yml discovers."""

    def test_rule_id_resolves_under_sgconfig(self) -> None:
        with _probe("tests/unit", _KNOWN_BAD) as rel_path:
            proc = _scan(rel_path, rule_args=("--filter", f"^{re.escape(RULE_ID)}$"))
            matches = _matches(proc)
        assert matches, (
            f"`ast-grep scan --filter ^{RULE_ID}$` found nothing: the rule is not in a "
            f"ruleDirs entry of sgconfig.yml, so the project-wide scan and the pre-commit "
            f"hook would never run it.\n--- rc={proc.returncode} stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )


class TestLiveTreeAndExemptions:
    """(f) The tree is clean, and every exemption is a live violation."""

    def test_tests_tree_has_no_unexempted_credential_construction(self) -> None:
        proc = _scan("tests/", globs=(_PROBE_EXCLUDE_GLOB,))
        matches = _matches(proc)
        assert matches == [], (
            f"{len(matches)} inline credential-header constructions remain in tests/. Route "
            f"each through the shared test-credential producer in tests/harness/client.py, or "
            f"exempt it with a reason and record it in _RECORDED_EXEMPTIONS:\n  " + "\n  ".join(_sites(matches))
        )

    def test_suppressed_set_equals_recorded_exemptions(self) -> None:
        directive = re.compile(rf"#\s*ast-grep-ignore:\s*{re.escape(RULE_ID)}\b")
        # This module is excluded: it spells the directive inside string
        # literals as TEST DATA (TestExemptionForm), which is not an exemption.
        this_module = str(Path(__file__).resolve().relative_to(repo_root()))
        found = {
            str(path.relative_to(repo_root()))
            for path in (repo_root() / "tests").rglob("*.py")
            if directive.search(path.read_text(encoding="utf-8", errors="ignore"))
        } - {this_module}
        assert found == set(_RECORDED_EXEMPTIONS), (
            "the set of files suppressing this rule drifted from _RECORDED_EXEMPTIONS.\n"
            f"  unrecorded (add with a reason, or migrate): {sorted(found - set(_RECORDED_EXEMPTIONS))}\n"
            f"  recorded but no longer suppressing (delete the row): "
            f"{sorted(set(_RECORDED_EXEMPTIONS) - found)}"
        )

    def test_each_exemption_is_a_real_violation_without_its_suppression(self) -> None:
        directive = re.compile(r"#\s*ast-grep-ignore:[^\n]*")
        vacuous: list[str] = []
        for rel in sorted(_RECORDED_EXEMPTIONS):
            source = (repo_root() / rel).read_text(encoding="utf-8")
            with _probe("tests/unit", directive.sub("", source)) as probe_path:
                if not _matches(_scan(probe_path)):
                    vacuous.append(rel)
        assert vacuous == [], (
            "these files are exempted but do not violate the rule once their suppression "
            f"comment is removed — the exemption is prose, delete it: {vacuous}"
        )


class TestExemptionForm:
    """The suppression form our exemptions depend on, pinned executably.

    ast-grep suppresses on `# ast-grep-ignore: <id>`, but appending the reason on
    the SAME line as the directive breaks the suppression silently — measured,
    and the reason this convention puts the justification on the PRECEDING line.
    An ast-grep upgrade that changes either behaviour changes what every
    exemption in this tree means, so it is graded rather than written down.
    """

    def test_reason_on_the_preceding_line_suppresses(self) -> None:
        source = (
            "def build(token):\n"
            "    # outbound webhook credential: seller -> buyer, not a request we construct\n"
            f"    # ast-grep-ignore: {RULE_ID}\n"
            '    return {"Authorization": f"Bearer {token}"}\n'
        )
        with _probe("tests/unit", source) as rel_path:
            matches = _matches(_scan(rel_path))
        assert matches == [], f"the documented exemption form did not suppress: {_sites(matches)}"

    def test_reason_on_the_directive_line_does_not_suppress(self) -> None:
        source = (
            "def build(token):\n"
            f"    # ast-grep-ignore: {RULE_ID} - outbound webhook credential\n"
            '    return {"Authorization": f"Bearer {token}"}\n'
        )
        with _probe("tests/unit", source) as rel_path:
            matches = _matches(_scan(rel_path))
        assert matches, (
            "a reason appended to the directive line now suppresses. It did not when this "
            "convention was chosen, which is why reasons go on the preceding line; if "
            "ast-grep changed, update the convention and this test together."
        )
