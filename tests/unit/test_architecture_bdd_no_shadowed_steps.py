"""Guard: one Gherkin sentence must have exactly one meaning.

Two checks, both behavioral (they read the real ``pytestbdd_stepdef_*`` fixtures
pytest-bdd built at import time, not source text), over every module listed in
``tests/bdd/conftest.py``'s ``pytest_plugins``.

Check 1 — NAME IDENTITY (``test_no_shadowed_step_registrations``)
    pytest-bdd turns each ``@given/@when/@then`` into a module-level fixture named
    ``pytestbdd_stepdef_<type>_<parsed text>``. When two registered modules declare
    the same step text, the two fixtures collide by name; pytest resolves the
    collision by plugin registration order, so ONE definition wins and the other —
    which usually carries *different* verification logic — is silently dead.

Check 2 — MATCH OVERLAP (``test_no_domain_exact_text_shadows_generic_parser``)
    Name identity is blind to the more common shape of the same disease: a domain
    module registers an EXACT-TEXT step whose sentence a ``generic`` module's
    *parser* also matches. The two fixtures have different names, so check 1 sees
    nothing, yet exactly one of the two bodies grades the scenario and the loser is
    dead code. This check runs every step line in ``tests/bdd/features/`` through
    every registered parser (filtered by step type first, exactly as production does
    at ``pytest_bdd/scenario.py``) and fails when a line is matched by BOTH a
    non-generic module's exact-text step AND a ``tests.bdd.steps.generic.*`` parser.

Why check 2 is scoped to *that* shape and not "2+ modules match one line":
measured at HEAD over all feature step lines x all registered parsers, the broad
rule fires on 11 cross-module collision classes. Three of them are a domain module
deliberately narrowing a generic sentence, and they resolve only by conftest
``pytest_plugins`` ORDER — reordering that list silently changes grading. Landing
the broad rule would therefore force ~10 behavioural winner-decisions in
UC-002/003/004/006 grading. The narrowed rule names one disease and needs NO
allowlist.

Deliberately OUT OF SCOPE here, to be raised in follow-up work rather than parked
in an allowlist (an allowlist would re-admit the disease):
  * generic-vs-domain match overlap in general — 5 classes at HEAD, of which this
    check grades only the exact-text subset;
  * cross-module match overlap in general — 11 classes at HEAD, including the three
    order-dependent deliberate-narrowing classes described above;
  * INTRA-module ambiguity — 34 further step texts across 7 modules where two
    parsers in the SAME module match one sentence. No "2+ modules" rule can see
    these.
  * module-LOCAL steps in scenario-binding test files (``tests/bdd/test_uc*.py``).
    A scenario-binding module cannot be imported outside a pytest session
    (``pytest_bdd.scenario.get_from_ini`` reads ``CONFIG_STACK[-1]``), so a plain
    unit-test guard can only cover ``pytest_plugins`` modules; covering test modules
    needs a collection-time hook.

All three limits are tracked on GH #1938, which owns the duplicate-step class and
carries the measurement behind them (11 cross-module collision classes, 34 further
intra-module texts, and the fact that for the deliberate-narrowing classes the winner
is decided purely by ``pytest_plugins`` registration ORDER). They are declared here
rather than allowlisted because an allowlist would re-admit the disease this guard
exists to remove.

Neither check has an allowlist, by design.

beads: salesagent-g4cm (the original name-identity guard)
GH #1941 — the match-overlap check added below
"""

from __future__ import annotations

import ast
import importlib
import re
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from pytest_bdd import parsers

_CONFTEST = Path(__file__).resolve().parents[1] / "bdd" / "conftest.py"
_FEATURES_DIR = Path(__file__).resolve().parents[1] / "bdd" / "features"

# pytest-bdd names every step fixture with this prefix.
_STEPDEF_PREFIX = "pytestbdd_stepdef_"

# Step modules under this package own the shared Gherkin vocabulary. A module
# outside it must not re-register a sentence one of these already matches.
_GENERIC_PACKAGE = "tests.bdd.steps.generic."

# Step texts intentionally registered by 2+ imported modules. MUST stay empty —
# a shadowed step means one verification body is dead. Fix the collision (pick a
# winner, delete the redundant one, or give the domain step distinct text)
# rather than allowlisting it.
_ALLOWED_SHADOWS: set[str] = set()


def _registered_step_plugins() -> list[str]:
    """Return the ``pytest_plugins`` step modules declared in bdd/conftest.py."""
    tree = ast.parse(_CONFTEST.read_text(), filename=str(_CONFTEST))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytest_plugins":
                    return [
                        el.value for el in node.value.elts if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    ]
    raise AssertionError("pytest_plugins not found in tests/bdd/conftest.py")


def _scan_shadowed_steps() -> dict[str, list[str]]:
    """Map each step-fixture name to the imported modules that register it.

    Only names registered by 2+ modules (i.e. genuine shadows) are returned.
    """
    registry: dict[str, list[str]] = defaultdict(list)
    for dotted in _registered_step_plugins():
        module = importlib.import_module(dotted)
        short = dotted.split(".")[-1]
        for attr in vars(module):
            if attr.startswith(_STEPDEF_PREFIX):
                registry[attr].append(short)

    return {
        name[len(_STEPDEF_PREFIX) :]: mods
        for name, mods in registry.items()
        if len(mods) > 1 and name[len(_STEPDEF_PREFIX) :] not in _ALLOWED_SHADOWS
    }


class _StepDef(NamedTuple):
    """One registered pytest-bdd step, as the resolver sees it."""

    module: str
    fixture: str
    step_type: str | None
    parser: parsers.StepParser

    @property
    def is_generic(self) -> bool:
        return self.module.startswith(_GENERIC_PACKAGE)

    @property
    def is_exact_text(self) -> bool:
        """True when the step was declared with a plain string, not a parser."""
        return isinstance(self.parser, parsers.string)


def _step_context(obj: object, module: str, attr: str):
    """Return the ``StepFunctionContext`` pytest-bdd attached to a step fixture.

    Unwraps defensively: pytest >= 8.4 wraps the step function in a
    ``FixtureFunctionDefinition`` that carries the context both directly and on
    ``._fixture_function``. RAISES rather than returning ``None`` when neither
    holds it — a guard that silently scans zero parsers passes vacuously, and a
    pytest minor bump changing the fixture shape is exactly how that happens.
    """
    context = getattr(obj, "_pytest_bdd_step_context", None)
    if context is None:
        context = getattr(getattr(obj, "_fixture_function", None), "_pytest_bdd_step_context", None)
    assert context is not None, (
        f"Cannot reach the pytest-bdd step context on {module}.{attr} "
        f"(type {type(obj).__name__}). The installed pytest/pytest-bdd changed the "
        f"step-fixture shape; this guard must be updated, not skipped — otherwise it "
        f"scans zero parsers and passes vacuously."
    )
    return context


def _registered_step_defs() -> list[_StepDef]:
    """Every step pytest-bdd registered from the ``pytest_plugins`` modules."""
    step_defs: list[_StepDef] = []
    for dotted in _registered_step_plugins():
        module: ModuleType = importlib.import_module(dotted)
        for attr, obj in vars(module).items():
            if not attr.startswith(_STEPDEF_PREFIX):
                continue
            context = _step_context(obj, dotted, attr)
            step_defs.append(_StepDef(module=dotted, fixture=attr, step_type=context.type, parser=context.parser))
    return step_defs


class _FeatureLine(NamedTuple):
    """One Gherkin step line, with the step type pytest-bdd will resolve it as."""

    path: Path
    lineno: int
    step_type: str
    text: str


_STEP_KEYWORDS = {"given": "given", "when": "when", "then": "then"}
_CONTINUATION_KEYWORDS = {"and", "but", "*"}
_BLOCK_KEYWORDS = (
    "feature:",
    "rule:",
    "background:",
    "scenario:",
    "scenario outline:",
    "scenario template:",
    "example:",
    "examples:",
)
_STEP_RE = re.compile(r"^(Given|When|Then|And|But|\*)\s+(\S.*)$")
# Scenario-outline placeholders are substituted per Examples row; the raw line is
# not a sentence any parser is asked to match.
_PLACEHOLDER_RE = re.compile(r"<[^<>]+>")


def _feature_step_lines() -> list[_FeatureLine]:
    """Every concrete step line in ``tests/bdd/features/``, typed as pytest-bdd types it."""
    lines: list[_FeatureLine] = []
    for path in sorted(_FEATURES_DIR.rglob("*.feature")):
        current_type: str | None = None
        in_docstring = False
        for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
            stripped = raw.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring or not stripped or stripped.startswith(("#", "@", "|")):
                continue
            if stripped.lower().startswith(_BLOCK_KEYWORDS):
                current_type = None
                continue
            match = _STEP_RE.match(stripped)
            if match is None:
                continue
            keyword, text = match.group(1).lower(), match.group(2).strip()
            if keyword in _STEP_KEYWORDS:
                current_type = _STEP_KEYWORDS[keyword]
            elif keyword not in _CONTINUATION_KEYWORDS or current_type is None:
                continue
            if _PLACEHOLDER_RE.search(text):
                continue
            lines.append(_FeatureLine(path=path, lineno=lineno, step_type=current_type, text=text))
    return lines


class _MatchOverlapScan(NamedTuple):
    """Result of the match-overlap scan, including its own non-vacuity evidence."""

    parser_count: int
    line_count: int
    matched_line_count: int
    # (step text, offending exact-text module) -> (generic modules, example sites)
    overlaps: dict[tuple[str, str], tuple[list[str], list[str]]]


def _scan_domain_exact_text_over_generic() -> _MatchOverlapScan:
    """Find feature lines matched by both a domain exact-text step and a generic parser."""
    step_defs = _registered_step_defs()
    feature_lines = _feature_step_lines()

    overlaps: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    matched_line_count = 0
    for line in feature_lines:
        # Production resolves on step TYPE first (pytest_bdd/scenario.py); comparing
        # across types reports phantom overlaps.
        matched = [sd for sd in step_defs if sd.step_type == line.step_type and sd.parser.is_matching(line.text)]
        if not matched:
            continue
        matched_line_count += 1

        generic = sorted({sd.module for sd in matched if sd.is_generic})
        if not generic:
            continue
        for sd in matched:
            if sd.is_generic or not sd.is_exact_text:
                continue
            key = (line.text, sd.module)
            site = f"{line.path.name}:{line.lineno}"
            if key in overlaps:
                overlaps[key][1].append(site)
            else:
                overlaps[key] = (generic, [site])

    return _MatchOverlapScan(
        parser_count=len(step_defs),
        line_count=len(feature_lines),
        matched_line_count=matched_line_count,
        overlaps=overlaps,
    )


class TestBddNoShadowedSteps:
    """Structural guard: no step text registered by 2+ imported step modules."""

    def test_no_shadowed_step_registrations(self):
        """Every step text must be registered by at most one imported module.

        A step text registered by 2+ ``pytest_plugins`` modules means pytest-bdd
        silently picks one definition by registration order and discards the
        other's verification logic.
        """
        shadows = _scan_shadowed_steps()
        if not shadows:
            return

        lines = [f"\n  {text!r} registered by: {mods}" for text, mods in sorted(shadows.items())]
        assert not shadows, (
            f"Found {len(shadows)} step text(s) registered by 2+ imported modules "
            f"(silent shadowing — one verification body is dead):" + "".join(lines)
        )

    def test_no_domain_exact_text_shadows_generic_parser(self):
        """A non-generic module must not exact-text a sentence a generic parser matches.

        The generic module owns the shared vocabulary. When a domain module
        registers the same sentence as a plain string, pytest-bdd hands that
        scenario exactly one of the two bodies and the other is dead — so the
        sentence means one thing in most features and something else in one.
        Give the domain step distinct text, or delete it and let the generic
        parser be the sentence's single meaning.
        """
        scan = _scan_domain_exact_text_over_generic()

        # Non-vacuity. If a pytest/pytest-bdd bump changes the fixture shape, or the
        # feature-line reader stops recognising Gherkin, this guard would scan
        # nothing and pass — reporting green precisely where it cannot observe what
        # it was asked to grade.
        assert scan.parser_count > 0, "Scanned zero registered step parsers — the guard is broken, not green."
        assert scan.line_count > 0, f"Read zero step lines from {_FEATURES_DIR} — the guard is broken, not green."
        assert scan.matched_line_count > 0, (
            f"Ran {scan.line_count} feature step line(s) through {scan.parser_count} parser(s) "
            f"and NOTHING matched — parser resolution is broken, not clean."
        )

        if not scan.overlaps:
            return

        report = [
            f"\n  {text!r}"
            f"\n      exact-text step: {module}"
            f"\n      also matched by: {', '.join(generic)}"
            f"\n      feature line(s): {', '.join(sites)}"
            for (text, module), (generic, sites) in sorted(scan.overlaps.items())
        ]
        assert not scan.overlaps, (
            f"Found {len(scan.overlaps)} sentence(s) where a non-generic step module exact-texts "
            f"a sentence a {_GENERIC_PACKAGE}* parser already matches. One Gherkin sentence has "
            f"exactly one meaning — one of these two verification bodies is dead:" + "".join(report)
        )
