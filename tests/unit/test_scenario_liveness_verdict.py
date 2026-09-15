"""The liveness verdict is derived from what ran, not from how a reason is worded.

``harness_wired`` in ``test-results/bdd_scenario_liveness.json`` is what
``scripts/audit/scenario_liveness_join.py`` reads to decide whether a
storyboard-tagged scenario is actually graded. It used to be derived from the
xfail reason TEXT: ``_classify_reason`` buckets on the substrings "harness" and
"wired", everything else falls into a residual "ledgered" bucket, and "ledgered"
set ``harness_wired=True``.

Two blanket routes in ``tests/bdd/conftest.py`` abort their scenarios inside
fixture setup, so no step body ever runs — and both missed the tokens:

* ``uc010-not-wired`` says "harness wiring", and the token is "wired";
* ``uc006-unclassified`` contains neither token.

Both were therefore recorded as harness-wired having never executed a step, and
the audit join consumed that as coverage. Under-matching is the direction that
inflates a coverage report, and any rewording can cause it again.

These tests hold the fix: the verdict reads ``Observation.steps_executed``, a
fact ``pytest_bdd_before_step_call`` records, and the reason string is metadata
that can only ever select BETWEEN not-wired verdicts.
"""

from __future__ import annotations

import pytest

from tests.bdd.scenario_liveness import Observation, ScenarioLiveness, _classify_reason

#: Verbatim from ``tests/bdd/conftest.py``, the ``uc010-not-wired`` route's
#: ``xfail_reason``. Quoted rather than imported: the point is that THIS wording
#: used to change a verdict, so the test must keep saying it even if the route is
#: reworded or deleted.
UC010_NOT_WIRED = "UC-010 harness wiring not extended to this tag (dormant, never graded)"

#: Verbatim from the ``uc006-unclassified`` route's ``xfail_reason``.
UC006_UNCLASSIFIED = (
    "UC-006 UNCLASSIFIED: no row names this scenario, so nobody has decided what "
    "blocks it. Wire it, or give it a row naming its blocker -- do not leave it here"
)


def _verdict(reason: str, *, steps_executed: bool) -> ScenarioLiveness:
    """One scenario, one observation, the verdict that falls out."""
    record = ScenarioLiveness(scenario_id="T-UC-000-probe", feature="probe.feature")
    record.record_observation(
        Observation(
            transport="mcp",
            nodeid="tests/bdd/test_probe.py::test_probe[mcp]",
            outcome="xfailed",
            reason=reason,
            reason_category=_classify_reason(reason),
            steps_executed=steps_executed,
        )
    )
    return record


class TestNeverRanIsNeverWired:
    """A scenario that executed no step cannot be reported as harness-wired."""

    @pytest.mark.parametrize(
        ("route", "reason"),
        [("uc010-not-wired", UC010_NOT_WIRED), ("uc006-unclassified", UC006_UNCLASSIFIED)],
    )
    def test_blanket_route_reason_is_not_wired(self, route: str, reason: str) -> None:
        """Both live offenders. This fails when the verdict is read off the text.

        Each reason still lands in the residual "ledgered" bucket — that is the
        classifier's own behaviour and this test does not change it. What it pins
        is that "ledgered" no longer produces a WIRED verdict when nothing ran.
        """
        assert _classify_reason(reason) == "ledgered", (
            f"{route}: precondition — this reason is expected to fall into the residual bucket, "
            "which is what made it dangerous"
        )
        record = _verdict(reason, steps_executed=False)
        assert record.harness_wired is False, (
            f"{route}: a scenario aborted in fixture setup reported harness_wired="
            f"{record.harness_wired!r}. No step body ran, so it graded nothing."
        )

    def test_a_ledger_marker_xfail_stays_wired(self) -> None:
        """The other side of the discrimination, which the fix must not break.

        A ledgered known failure is a MARKER: the scenario runs, executes its
        steps, fails, and the marker converts that failure to an xfail. Steps ran,
        so it is wired and genuinely graded something. Only a fixture-level
        ``pytest.xfail()`` prevents steps from running, and that is the case the
        test above covers.
        """
        record = _verdict("e2e_rest: mock-incompatible scenario", steps_executed=True)
        assert record.harness_wired is True
        assert record.ledgered is True


class TestWordingCannotMoveTheVerdict:
    """Same structural facts, different sentences, same verdict."""

    @pytest.mark.parametrize("steps_executed", [True, False])
    def test_rewording_does_not_change_the_verdict(self, steps_executed: bool) -> None:
        """Four spellings of the same situation, including the token near-misses.

        "wired" / "wiring" / neither is exactly the axis the old classifier was
        sensitive to, so these four strings would have produced different verdicts
        for identical facts.
        """
        wordings = [
            "harness not wired for this tag",
            "harness wiring not extended to this tag",
            "nobody has decided what blocks this scenario",
            "",
        ]
        verdicts = {w: _verdict(w, steps_executed=steps_executed).harness_wired for w in wordings}
        assert len(set(verdicts.values())) == 1, (
            f"rewording moved the verdict with steps_executed={steps_executed}: {verdicts}"
        )

    def test_the_verdict_tracks_the_fact_that_did_change(self) -> None:
        """The control: with the wording held fixed, the structural fact decides.

        Without this, the test above passes for a verdict that is constant
        because it ignores everything — the assertion would hold if
        ``harness_wired`` were hard-coded.
        """
        reason = "harness wiring not extended to this tag"
        assert _verdict(reason, steps_executed=True).harness_wired is True
        assert _verdict(reason, steps_executed=False).harness_wired is False
