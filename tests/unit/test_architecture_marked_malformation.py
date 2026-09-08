"""Guard: a deliberately-malformed test payload is DECLARED, and the declaration is auditable.

Two mechanisms grade the core invariant — "a test payload the pinned model rejects is
either a declared malformation or a defect, and the difference is stated at the site
where the payload is written" — and this file is only one of them.

    THE RUNTIME GATE FINDS UNMARKED MALFORMATIONS.
    ``assert_declared_malformations`` (``tests/factories/malformed.py``), called from
    ``dispatch_request`` (``tests/bdd/steps/generic/_dispatch.py``) before ``json_safe``
    rebuilds the dicts, validates every dispatched item against the pinned model. It has
    to be a runtime gate and this file cannot take that job over: measured,
    ``ast.literal_eval`` succeeds on 0 of the 40 creative literals in
    ``uc006_sync_creatives.py`` (46 of 50 across ``--scope bdd``) — every one holds a
    Name, Attribute, Call or f-string — so a source-level validation gate would pass
    vacuously green over the file holding 80% of the subject.

    THIS FILE KEEPS THE DECLARATIONS AUDITABLE, and owns the shrink-only list of sites
    that are known to hold an undeclared malformation. It asserts that every
    ``malformed(...)`` call names a kind from the closed vocabulary and a non-empty
    reason — NOT that malformations are absent, which it has no way to know.

Consequently ``test_known_violations_not_stale`` reports STALE entries (a site got
declared, remove it) and never NEW ones. New violations are the runtime gate's to
report, and it reports them where they happen: at dispatch, in the failing scenario.

``KNOWN_VIOLATIONS`` was a HANDOFF, not a tolerance, and it is now EMPTY: all five
seeded sites carry a declaration. The runtime gate has no allowlist either: measured,
all five sit in scenarios that are xfail-dormant, so the gate fires zero times over
them and a tolerance would only mask the malformation on the day the scenario is wired.

Site census comes from ``scan()``/``SCOPES`` in
``scripts/audit/creative_literal_sites.py`` rather than a second definition of "site",
so the audit and the guard cannot disagree about what they are counting.

Structured on ``tests/unit/test_architecture_no_packages_field_literal.py`` (the
allowlist-plus-staleness idiom, and exemption of a legitimate producer BY IDENTITY) and
``tests/unit/test_architecture_harness_identity_sentinel.py`` (the three-control
meta-test shape).
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from scripts.audit.creative_literal_sites import SCOPES, scan
from tests.factories.malformed import (
    GATED_ITEMS,
    MALFORMATION_KINDS,
    _Malformed,
    malformation_problems,
    malformed,
)
from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_guard_subject_resolves,
    assert_scanned_paths_exist,
    assert_violations_match_allowlist,
    iter_call_expressions,
    repo_root,
    safe_parse,
    walk_with_enclosing_function,
)

MARKER_NAME = "malformed"

# Census sites that dispatch a payload the pinned model rejects and carry no
# declaration yet. Keyed by (relative_path, enclosing_function). MUST ONLY SHRINK.
#
# EMPTY, and it stays empty. The 5 of 8 FIXABLE_NOW sites this set was seeded with
# (salesagent-hz7di.2's scan; 4954/4974/5347 are repaired by a later Given and were
# correctly never listed) all carry a ``malformed(...)`` declaration as of
# salesagent-hz7di.4, in tests/bdd/steps/domain/uc006_sync_creatives.py:
#
#     given_creative_with_known_format_no_media_url   absent_key
#     given_creative_with_name_no_format              explicit_none
#     given_creative_invalid_schema                   wrong_type
#     given_creative_with_no_format_id                absent_key
#     given_creative_with_invalid_format_id           semantic
#
# The last of those was handed over as a DEAD STEP to delete rather than mark. It is
# not dead: no feature file holds its literal text, but
# "Format validation — <partition>" substitutes ``format_setup`` = ``no format_id``
# into ``And a creative with <format_setup>``, which renders to exactly this step's
# name and resolves to it (checked against pytest-bdd's registered parsers). It grades
# ``test_format_validation__partition[a2a|mcp|rest-missing_format_id-...]``, all three
# xfail-dormant at SETUP — so the prescribed "did any scenario turn xfail" check would
# have passed vacuously over the deletion. It is marked instead.
#
# There is no runtime tolerance list to match this one: see the measurement recorded in
# tests/factories/malformed.py.
KNOWN_VIOLATIONS: set[tuple[str, str]] = set()

#: Sites ``scan()`` reports that are not payloads at all, excluded BY IDENTITY rather
#: than by allowlist: an allowlist entry says "known debt, will shrink", and these are
#: category errors that will never shrink. The site definition is a key-overlap
#: heuristic (>=2 of a 9-key set), so it catches dicts that never travel to a model.
#:
#: ``tests/factories/creative_asset.py`` is exempt on the same grounds — it is the
#: definition, not tolerated debt — and is additionally outside ``--scope bdd``, so it
#: is not listed here; a list entry that never matches would go stale by construction.
EXEMPT_BY_IDENTITY: dict[tuple[str, str], str] = {
    (
        "tests/bdd/steps/generic/given_entities.py",
        "given_seller_creative_agent_various_assets",
    ): "ctx['creative_agent_formats'] entries are FORMAT descriptors, not creatives; "
    "the name+assets key overlap is what the heuristic sees. Validating a format "
    "descriptor against a creative request is a category error.",
    (
        "tests/bdd/steps/domain/uc026_package_media_buy.py",
        "given_product_with_pricing",
    ): "_LABEL_SPEC rows are spread as ORM kwargs into PricingOptionFactory(...). "
    "is_fixed is a DB column, not a PricingOption schema field, which is exactly why "
    "the schema reports extra_forbidden on it.",
}


# ---------------------------------------------------------------------------
# Detector: is every declaration auditable?
# ---------------------------------------------------------------------------


def _string_constant(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _marker_argument(call: ast.Call, position: int, name: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def find_unauditable_markers(tree: ast.Module) -> list[int]:
    """Line numbers of ``malformed(...)`` calls whose kind or reason cannot be audited.

    A marker is auditable only when both are literals at the site: a non-literal kind
    cannot be checked against the vocabulary, and a non-literal reason is a promise
    that some other line keeps.
    """
    bad: list[int] = []
    for call in iter_call_expressions(tree, MARKER_NAME):
        kind = _string_constant(_marker_argument(call, 0, "kind"))
        why = _string_constant(_marker_argument(call, 1, "why"))
        if kind not in MALFORMATION_KINDS or not (why or "").strip():
            bad.append(call.lineno)
    return bad


# ---------------------------------------------------------------------------
# Site census (shared with the audit script)
# ---------------------------------------------------------------------------


def _absolute(scope: str) -> list[str]:
    """``SCOPES[scope]`` anchored at the repo root — ``scan()`` globs relative to cwd."""
    return [str(repo_root() / pattern) for pattern in SCOPES[scope]]


def _rel(path: str) -> str:
    return str(Path(path).resolve().relative_to(repo_root()))


def _site_lines_by_file(scope: str) -> dict[str, set[int]]:
    creatives, pricing = scan(_absolute(scope))
    lines: dict[str, set[int]] = {}
    for site in [*creatives, *pricing]:
        lines.setdefault(_rel(site["file"]), set()).add(site["line"])
    return lines


def _marker_spans(tree: ast.Module) -> list[tuple[int, int]]:
    """Line ranges covered by a ``malformed(...)`` call — the technique ``factory_spans`` uses."""
    return [(call.lineno, call.end_lineno or call.lineno) for call in iter_call_expressions(tree, MARKER_NAME)]


def unmarked_site_functions(scope: str = "bdd") -> set[tuple[str, str]]:
    """``(relative_path, enclosing_function)`` for every census site not inside a marker."""
    found: set[tuple[str, str]] = set()
    for rel_path, linenos in _site_lines_by_file(scope).items():
        tree = safe_parse(repo_root() / rel_path)
        if tree is None:
            continue
        spans = _marker_spans(tree)
        for node, func in walk_with_enclosing_function(tree):
            if not isinstance(node, ast.Dict) or node.lineno not in linenos:
                continue
            if (rel_path, func) in EXEMPT_BY_IDENTITY:
                continue
            if not any(lo <= node.lineno <= hi for lo, hi in spans):
                found.add((rel_path, func))
    return found


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


@pytest.mark.arch_guard
def test_every_declaration_is_auditable() -> None:
    """Every ``malformed(...)`` in the test tree names a known kind and a real reason."""
    # The whole test tree, not just the census scope: a declaration written anywhere
    # must be auditable, and a marker outside --scope bdd is exactly the one nobody
    # would think to look at.
    violations: list[str] = []
    for path in sorted((repo_root() / "tests").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        tree = safe_parse(path)
        if tree is None:
            continue
        rel_path = str(path.relative_to(repo_root()))
        violations.extend(f"  {rel_path}:{lineno}" for lineno in find_unauditable_markers(tree))
    assert not violations, (
        f"{len(violations)} malformed(...) call(s) cannot be audited. The kind must be a "
        f"literal from {sorted(MALFORMATION_KINDS)} and the reason a non-empty literal — "
        "a bare or indirect marker is an opt-out, not a justification:\n" + "\n".join(violations)
    )


@pytest.mark.arch_guard
def test_known_violations_not_stale() -> None:
    """Every allowlisted entry still names an undeclared census site. Must only shrink."""
    unmarked = unmarked_site_functions()
    found = {entry for entry in KNOWN_VIOLATIONS if entry in unmarked}
    assert_violations_match_allowlist(
        found,
        KNOWN_VIOLATIONS,
        fix_hint=(
            "An entry goes stale when its site is wrapped in malformed(...) or deleted "
            "— remove it then. KNOWN_VIOLATIONS is never grown: an undeclared "
            "malformation is reported by the runtime gate at dispatch, in the failing "
            "scenario, not by this file."
        ),
    )


@pytest.mark.arch_guard
def test_identity_exemptions_still_name_real_sites() -> None:
    """An exemption that stops matching is a stale claim about the tree, not a free pass."""
    assert_scanned_paths_exist(
        [path for path, _ in EXEMPT_BY_IDENTITY],
        why="the identity exemptions in this guard would silently cover nothing.",
    )
    census = _site_lines_by_file("bdd")
    orphans: list[str] = []
    for rel_path, func in EXEMPT_BY_IDENTITY:
        tree = safe_parse(repo_root() / rel_path)
        linenos = census.get(rel_path, set())
        hit = tree is not None and any(
            isinstance(node, ast.Dict) and node.lineno in linenos and enclosing == func
            for node, enclosing in walk_with_enclosing_function(tree)
        )
        if not hit:
            orphans.append(f"  {rel_path}:{func}()")
    assert not orphans, (
        "EXEMPT_BY_IDENTITY names site(s) the census no longer reports. Remove the entry "
        "— an exemption for something that is not there teaches the next reader that a "
        "real site is tolerated:\n" + "\n".join(orphans)
    )


@pytest.mark.arch_guard
def test_guard_subjects_resolve() -> None:
    """The names this guard scans for still exist — a rename must fail loudly, not silently."""
    assert_guard_subject_resolves(
        "tests.factories.malformed",
        "malformed",
        "MALFORMATION_KINDS",
        "assert_declared_malformations",
        why="nothing would declare or grade a deliberate malformation.",
    )
    assert_guard_subject_resolves(
        "scripts.audit.creative_literal_sites",
        "scan",
        "SCOPES",
        why="this guard would invent a second definition of 'site' and drift from the audit.",
    )
    assert_guard_subject_resolves(
        "tests.bdd.steps.generic._dispatch",
        "dispatch_request",
        why="the runtime gate would hang off nothing.",
    )


@pytest.mark.arch_guard
def test_gated_creative_model_is_the_pinned_request_item() -> None:
    """The gate validates against the DTO's OWN item type, derived rather than declared."""
    from src.core.schemas.creative import SyncCreativesRequest

    item_models = get_args(SyncCreativesRequest.model_fields["creatives"].annotation)
    assert len(item_models) == 1, f"expected list[<one model>], got {item_models}"
    item_model = item_models[0]
    assert GATED_ITEMS["creatives"][0] is item_model, (
        f"The runtime gate validates creatives against {GATED_ITEMS['creatives'][0].__name__}, "
        f"but SyncCreativesRequest.creatives holds {item_model.__name__}. Grading a model the "
        "request does not use is how a request shape became a response shape once already."
    )


# ---------------------------------------------------------------------------
# Meta-tests — break it on purpose, as committed tests
# ---------------------------------------------------------------------------

_CONFORMANT_CREATIVE: dict[str, Any] = {
    "creative_id": "creative-meta-001",
    "name": "Conformant",
    "format_id": {"id": "display_300x250", "agent_url": "https://agent.test"},
    "assets": {"image": [{"asset_type": "image", "url": "https://cdn.test/a.png", "width": 300, "height": 250}]},
}


def _rejected_creative(creative_id: str = "creative-meta-001") -> dict[str, Any]:
    """The conformant creative minus ``assets`` — measured REJECTED by the pin (``Field required``)."""
    return {**{k: v for k, v in _CONFORMANT_CREATIVE.items() if k != "assets"}, "creative_id": creative_id}


@pytest.mark.arch_guard
def test_positive_control_static_detector_catches_unauditable_markers() -> None:
    """The static detector flags every shape of unauditable declaration."""
    assert_detector_catches_ast_snippets(
        find_unauditable_markers,
        snippets={
            "kind-not-in-vocabulary": 'x = malformed("typo_kind", "a real reason", {"a": 1})\n',
            "reason-empty": 'x = malformed("wrong_type", "   ", {"a": 1})\n',
            "reason-missing": 'x = malformed("wrong_type")\n',
            "kind-not-a-literal": 'x = malformed(KIND, "a real reason", {"a": 1})\n',
            "reason-not-a-literal": 'x = malformed("wrong_type", REASON, {"a": 1})\n',
        },
    )


@pytest.mark.arch_guard
def test_negative_control_conformant_declaration_not_flagged() -> None:
    """A well-formed declaration — positional or keyword — is left alone."""
    source = (
        'a = malformed("wrong_type", "assets is a string where the pin requires an object", {"assets": "x"})\n'
        'b = malformed(kind="absent_key", why="no format_id key at all", payload={"name": "n"})\n'
    )
    assert find_unauditable_markers(ast.parse(source, filename="<known-good>")) == []


@pytest.mark.arch_guard
def test_positive_control_runtime_gate_flags_unmarked_malformation() -> None:
    """An undeclared item the pinned model rejects is reported, with the pydantic reason."""
    payload = _rejected_creative("creative-meta-unmarked-001")
    problems = malformation_problems({"creatives": [payload]})
    assert len(problems) == 1, problems
    assert "creative-meta-unmarked-001" in problems[0]
    assert "assets" in problems[0]


@pytest.mark.arch_guard
def test_positive_control_runtime_gate_accepts_the_marked_form() -> None:
    """The SAME rejected bytes, declared, pass — and stay byte-identical on the way."""
    payload = _rejected_creative()
    declared = malformed("absent_key", "no assets key: exercises the preview-failure branch", payload, pin_rejects=True)
    assert malformation_problems({"creatives": [declared]}) == []
    assert isinstance(declared, _Malformed)
    assert dict(declared) == payload, "the declaration must not alter what reaches the wire"


@pytest.mark.arch_guard
def test_negative_control_runtime_gate_passes_a_conformant_literal() -> None:
    """A conformant creative is NOT flagged — the gate asks the model, not for markers."""
    assert malformation_problems({"creatives": [_CONFORMANT_CREATIVE]}) == []


@pytest.mark.arch_guard
def test_scenario_level_control_dispatch_request_refuses_an_unmarked_malformation() -> None:
    """The gate is wired into the dispatch seam, ahead of the try/except that would eat it.

    The scenario-level equivalent of the controls above: a step that hands
    ``dispatch_request`` an undeclared malformation fails the scenario, and the same
    payload declared reaches the transport untouched.
    """
    from tests.bdd.steps.generic._dispatch import dispatch_request
    from tests.harness.transport import Transport

    dispatched: list[Any] = []

    def call_via(transport: Any, **kwargs: Any) -> SimpleNamespace:
        dispatched.append(kwargs["creatives"])
        return SimpleNamespace(is_error=False, wire_response=None)

    ctx: dict[str, Any] = {"env": SimpleNamespace(call_via=call_via), "transport": Transport.MCP}

    payload = _rejected_creative()
    with pytest.raises(AssertionError, match="not declared malformed"):
        dispatch_request(ctx, creatives=[payload])
    assert dispatched == [], "the gate must refuse BEFORE anything reaches the transport"

    declared = malformed("absent_key", "no assets key: exercises the preview-failure branch", payload, pin_rejects=True)
    dispatch_request(ctx, creatives=[declared])
    assert dispatched == [[declared]]
    assert dict(dispatched[0][0]) == payload


# ---------------------------------------------------------------------------
# The declaration is graded against the pin's ACTUAL verdict — both directions
# ---------------------------------------------------------------------------
#
# ``kind`` is the SHAPE of the wrongness; whether the pinned model catches it is an
# INDEPENDENT axis, which is why ``pin_rejects`` carries it rather than being derived
# from a partition of kinds. Measured counterexample to any such partition:
# ``uc006_sync_creatives.py:6190`` is declared ``semantic`` and the pin REJECTS it
# (format_id.id must match ``^[a-zA-Z0-9_-]+$``), while a DIFFERENT semantic case — an
# unknown but well-formed format id — the pin ACCEPTS.
#
#     pin_rejects=True  and the pin ACCEPTS   -> REPAIRED malformation. Report it,
#                                                naming the site and the kind.
#     pin_rejects=False and the pin REJECTS   -> MIS-DECLARED. Report it, quoting the
#                                                pydantic error.
#     the pin's verdict matches the declaration -> nothing to report.
#
# WHY IT IS NEEDED: the gate USED TO skip every declared item without validating it, so a
# declaration that had stopped being true was invisible. Once a ``CreativeAssetRequest``
# factory exists, ``malformed("absent_key", why, Factory.payload())`` declares an absence
# the factory has just supplied — the marker lies and the gate says nothing.
#
# THE UNDECLARED HALF IS UNCHANGED and is anchored by two controls already in this file
# rather than restated here: ``test_positive_control_runtime_gate_flags_unmarked_malformation``
# (undeclared + pin-rejected still fails) and
# ``test_negative_control_runtime_gate_passes_a_conformant_literal`` (undeclared +
# conformant still passes). A declaration stays REQUIRED only on items the pin rejects
# and is never demanded on a conformant payload — b341x.1's deliberate asymmetry, which
# grading declared items in both directions does not disturb.


@pytest.mark.arch_guard
@pytest.mark.parametrize(
    ("declared", "must_report"),
    [
        pytest.param(
            malformed(
                "absent_key",
                "declares the assets key absent — but these bytes carry it, which is exactly "
                "what a factory default does to a malformation",
                {**_CONFORMANT_CREATIVE, "creative_id": "creative-meta-repaired-001"},
                pin_rejects=True,
            ),
            ("creatives[0]", "creative-meta-repaired-001", "absent_key"),
            id="repaired",
        ),
        pytest.param(
            malformed(
                "absent_key",
                "claims the pin tolerates a creative with no assets key; measured, it does not",
                _rejected_creative("creative-meta-misdeclared-001"),
                pin_rejects=False,
            ),
            ("creatives[0]", "creative-meta-misdeclared-001", "Field required"),
            id="mis-declared",
        ),
        pytest.param(
            malformed(
                "absent_key",
                "no assets key: exercises the preview-failure branch",
                _rejected_creative("creative-meta-honest-reject-001"),
                pin_rejects=True,
            ),
            (),
            id="honest-rejection",
        ),
        pytest.param(
            malformed(
                "empty_string",
                "an empty name is conformant to the pin and wrong downstream, which is the scenario's subject",
                {**_CONFORMANT_CREATIVE, "creative_id": "creative-meta-honest-accept-001", "name": ""},
                pin_rejects=False,
            ),
            (),
            id="honest-acceptance",
        ),
    ],
)
def test_declaration_is_graded_against_the_pins_actual_verdict(
    declared: _Malformed, must_report: tuple[str, ...]
) -> None:
    """A DECLARED item is validated rather than skipped, and both disagreements fail."""
    problems = malformation_problems({"creatives": [declared]})
    if not must_report:
        assert problems == [], (
            f"the declaration agrees with the pin (pin_rejects={declared.pin_rejects}), so the "
            "gate must stay silent:\n" + "\n".join(problems)
        )
        return
    assert len(problems) == 1, (
        f"a declaration that disagrees with the pin (pin_rejects={declared.pin_rejects}) must be "
        f"reported exactly once; got {len(problems)}. Skipping declared items is how a "
        "declaration that has stopped being true stays invisible:\n" + "\n".join(problems)
    )
    missing = [needle for needle in must_report if needle not in problems[0]]
    assert not missing, f"the report omits {missing}, so nobody can act on it:\n{problems[0]}"
