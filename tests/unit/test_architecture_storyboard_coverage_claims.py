"""Structural guard: the coverage map may not publish a claim as a measurement.

Two defects in ``scripts/audit/storyboard_coverage_map.py``, both of the shape this
epic (salesagent-v03pe) exists for — an instrument answering a question it cannot
answer, confidently, while consumers treat the answer as complete.

**The domain was declared, not derived.** ``ADVERTISED_TOOLS`` was a hand-maintained
set, and it decided ON-PATH vs OFF-PATH through the storyboard schema's ``required_tools``
any-of gate — i.e. it decided the DENOMINATOR every count downstream is quoted over, and
the domain of the one ``make quality`` gate wired to this module
(``test_architecture_storyboard_issue_map.py::test_every_on_path_storyboard_is_triaged``).
Measured at the 3.1.1 pin it had drifted in both directions: it claimed
``activate_signal``, ``get_signals`` and ``list_authorized_properties``, which the tool
registry does not implement, and omitted ``complete_task``, ``get_task_status`` and
``list_tasks``, which it does. The three phantom signals tools put three storyboards
ON-PATH — 48 checks — so the triage gate enforced a conformance path wider than the
agent has tools for, and defended the difference with its own green.

**A tag claim was published as coverage.** ``covered_by`` is presence of a
``@storyboard-v3.1`` tag plus a resolvable ``@source`` footer. A tagged scenario with
zero bound step definitions counted as coverage — the exact defect
``scripts/audit/scenario_liveness_join.py`` was written to fix and
``storyboard_check_index.py`` already consumes. This module grades the join and the
three-state verdict it produces: LIVE, CLAIMED-ONLY, and NOT-MEASURED when no BDD run
was joined at all. NOT-MEASURED is a verdict, never folded into a passing side.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_coverage_map, storyboard_spec  # noqa: E402


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_advertised_tools_are_read_from_the_live_tool_registry() -> None:
    """The AST reader must see exactly the tools the registry declares.

    ``advertised_tools`` reads ``src/core/tools/registry.py`` statically, because the
    audit scripts must run with no application dependencies resolved. That reader can
    drift from the real declaration — a renamed dict, a row added by ``update()``, a
    computed key — and a SHORT tool set silently narrows the conformance path, which is
    the failure the derivation exists to end. This is the only test that compares the
    static read against the live mapping.
    """
    from src.core.tools.registry import TOOLS

    assert storyboard_coverage_map.advertised_tools(REPO_ROOT) == set(TOOLS), (
        "the advertised-tool set the coverage map classifies with does not match "
        "src/core/tools/registry.py's TOOLS. Either the AST reader in "
        "storyboard_spec.advertised_tools no longer matches how the registry declares "
        "its rows, or the set is being declared somewhere instead of derived."
    )


def test_no_on_path_storyboard_is_gated_only_by_tools_we_do_not_implement() -> None:
    """The ON-PATH set the ``make quality`` triage gate enforces, graded against src/.

    Deliberately NOT written as "the derived set equals the derived set", which would be
    a tautology over whatever ``advertised_tools`` happens to return. It grades the
    classifier's OUTPUT: a storyboard whose ``required_tools`` gate is satisfied by no
    tool in ``TOOLS`` cannot be on our conformance path, however the tool set is spelled.
    Three storyboards failed this before the derivation landed —
    ``universal/error-compliance-signals.yaml``,
    ``universal/get-signals-pagination-integrity.yaml``,
    ``universal/schema-validation-signals.yaml`` — all three on ``get_signals`` /
    ``activate_signal``, and the real runner baseline quoted in the coverage map's
    docstring had already observed us advertising neither.
    """
    from src.core.tools.registry import TOOLS

    index = _index()
    implemented = set(TOOLS)
    offenders = sorted(
        rel
        for rel in storyboard_coverage_map.on_path_from_vendored_index(REPO_ROOT, index)
        if (required := set(index["storyboards"][rel].get("required_tools", []))) and not (required & implemented)
    )
    assert offenders == [], (
        f"{len(offenders)} storyboard(s) are classified ON-PATH while this agent implements none of "
        "their required_tools. The any-of gate cannot be satisfied, so the pinned runner would skip "
        "them as `not_applicable` — and every count quoted over the on-path set, plus the issue-map "
        "triage gate, is enforcing a conformance path the agent has no tools for:\n"
        + "\n".join(
            f"  {rel}: required_tools {sorted(index['storyboards'][rel]['required_tools'])}" for rel in offenders
        )
    )


@pytest.mark.parametrize(
    "registry_source,expected",
    [
        ("OTHER: dict[str, int] = {'a': 1}\n", "no module-level _TOOLS"),
        ("_TOOLS: dict[str, int] = {}\n", "is empty"),
        ("_TOOLS: dict[str, int] = {**other}\n", "not statically readable"),
        ("_TOOLS: dict[str, int] = other_mapping\n", "not a dict literal"),
    ],
)
def test_the_tool_registry_reader_refuses_what_it_cannot_read(
    tmp_path: Path, registry_source: str, expected: str
) -> None:
    """A reader that cannot see the declaration must raise, not return a small set.

    The failure mode being closed off: a silently short set takes storyboards OFF-PATH,
    which is invisible — nothing downstream can tell "we do not advertise this tool"
    apart from "the reader stopped working". Meta-test over each refusal branch: a guard
    that cannot fail is not a guard.
    """
    module = tmp_path / "src" / "core" / "tools"
    module.mkdir(parents=True)
    (module / "registry.py").write_text(registry_source, encoding="utf-8")
    with pytest.raises(storyboard_spec.StoryboardAuditError, match=expected):
        storyboard_spec.advertised_tools(tmp_path)


# ── The claim/coverage split ────────────────────────────────────────────────


def _row(status: str, coverage: str, covered_by: list[str] | None = None) -> dict:
    return {
        "storyboard": f"universal/{coverage.lower()}.yaml",
        "status": status,
        "coverage": coverage,
        "covered_by": covered_by if covered_by is not None else (["T-X"] if coverage != "NONE" else []),
    }


def test_an_unclassified_storyboard_is_counted_rather_than_dropped() -> None:
    """``classify_gates`` can return UNKNOWN, and no total used to hold it.

    An UNKNOWN row was in ``storyboards`` and in none of the other numbers, so a tier
    the classifier does not recognise vanished between two totals that both read as
    complete. It is now its own number, on neither the on-path nor the off-path side.
    """
    rows = [
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_NONE),
        _row("UNKNOWN", storyboard_coverage_map.COVERAGE_NONE),
    ]
    totals = storyboard_coverage_map.coverage_totals(rows, liveness_measured=True)

    assert totals["unknown"] == 1, "an unclassified storyboard must be counted as unclassified"
    assert totals["on_path"] == 1, "an unclassified storyboard must not be counted as on path"
    assert totals["off_path"] == 0, "an unclassified storyboard must not be counted as off path"
    assert totals["storyboards"] == totals["on_path"] + totals["off_path"] + totals["gated"] + totals["unknown"], (
        "the four statuses must partition the examined storyboards — a verdict that is in the "
        "denominator and in no numerator is exactly how a row goes missing without a trace"
    )


def test_an_unmeasured_claim_is_never_counted_as_coverage() -> None:
    """No BDD run joined means no claim on the page has been shown to grade anything."""
    rows = [
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_NOT_MEASURED),
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_NONE),
    ]
    totals = storyboard_coverage_map.coverage_totals(rows, liveness_measured=False)

    assert totals["liveness_measured"] is False
    assert totals["on_path_coverage_not_measured"] == 1
    assert totals["on_path_covered_live"] == 0, "an unmeasured claim must not count as live coverage"
    assert totals["on_path_claimed_not_live"] == 0, (
        "an unmeasured claim must not count as a claim-only finding either — that is a statement "
        "about the scenario, and nothing was measured about it"
    )
    assert totals["on_path_uncovered"] == 1, "only the storyboard with no claim at all is uncovered"


def test_the_four_coverage_verdicts_partition_the_on_path_set() -> None:
    """Every on-path storyboard lands in exactly one verdict, and they sum to the whole."""
    rows = [
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_LIVE),
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_CLAIMED),
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_NOT_MEASURED),
        _row("ON-PATH", storyboard_coverage_map.COVERAGE_NONE),
        _row("OFF-PATH", storyboard_coverage_map.COVERAGE_NONE),
    ]
    totals = storyboard_coverage_map.coverage_totals(rows, liveness_measured=True)

    verdict_sum = (
        totals["on_path_covered_live"]
        + totals["on_path_claimed_not_live"]
        + totals["on_path_coverage_not_measured"]
        + totals["on_path_uncovered"]
    )
    assert verdict_sum == totals["on_path"] == 4, (
        f"the coverage verdicts sum to {verdict_sum} over an on-path set of {totals['on_path']}. "
        "A verdict outside the partition is a storyboard whose coverage nobody reports."
    )


def test_the_rendered_cell_never_shows_an_unmeasured_claim_as_plain_coverage() -> None:
    """The report is what a reader acts on; the verdict has to be IN the cell.

    A bare list of scenario ids is what made this column read as coverage.
    """
    live = storyboard_coverage_map.coverage_cell(storyboard_coverage_map.COVERAGE_LIVE, ["T-A"])
    claimed = storyboard_coverage_map.coverage_cell(storyboard_coverage_map.COVERAGE_CLAIMED, ["T-A"])
    unmeasured = storyboard_coverage_map.coverage_cell(storyboard_coverage_map.COVERAGE_NOT_MEASURED, ["T-A"])
    none = storyboard_coverage_map.coverage_cell(storyboard_coverage_map.COVERAGE_NONE, [])

    assert live == "`T-A` (LIVE)"
    assert "claim only" in claimed and "T-A" in claimed
    assert "NOT MEASURED" in unmeasured and "T-A" in unmeasured
    assert "NO SCENARIO" in none
    assert len({live, claimed, unmeasured, none}) == 4, "the four verdicts must render distinguishably"
