"""Cross-phrasing persistence-timing scenario map consistency (BR-RULE-020).

Two Given steps in tests/bdd/steps/generic/given_media_buy.py phrase the same
3 persistence-timing scenarios differently in Gherkin ("the persistence
timing scenario is auto_approve_adapter_success" vs "the persistence timing
scenario is: auto-approve success"). _PARTITION_MAP and _BOUNDARY_MAP used to
be two independently hand-typed dicts over the same (approval, adapter_result)
config space, with no test asserting they agreed — editing one row could
silently diverge from the other without any scenario failing loudly
(salesagent-1q8d.13). Both are now derived from one canonical
_PERSISTENCE_TIMING_SCENARIOS list; this pins that derivation stays correct
and that both phrasings for every scenario resolve identically.
"""

from __future__ import annotations

from tests.bdd.steps.generic.given_media_buy import (
    _BOUNDARY_MAP,
    _PARTITION_MAP,
    _PERSISTENCE_TIMING_SCENARIOS,
)


class TestPersistenceTimingScenarioMapsAgree:
    def test_partition_and_boundary_maps_have_same_row_count_as_canonical(self):
        assert len(_PARTITION_MAP) == len(_PERSISTENCE_TIMING_SCENARIOS)
        assert len(_BOUNDARY_MAP) == len(_PERSISTENCE_TIMING_SCENARIOS)

    def test_every_canonical_row_resolves_identically_through_both_phrasings(self):
        for row in _PERSISTENCE_TIMING_SCENARIOS:
            partition_resolved = _PARTITION_MAP[row["partition"]]
            boundary_resolved = _BOUNDARY_MAP[row["boundary"]]
            assert partition_resolved == row["resolved"], (
                f"_PARTITION_MAP[{row['partition']!r}] = {partition_resolved}, expected {row['resolved']}"
            )
            assert boundary_resolved == row["resolved"], (
                f"_BOUNDARY_MAP[{row['boundary']!r}] = {boundary_resolved}, expected {row['resolved']}"
            )

    def test_no_duplicate_resolved_tuples_across_scenarios(self):
        """Each of the 3 scenarios must be genuinely distinct — a duplicate
        (approval, adapter_result) tuple would mean two Gherkin phrasings
        that are supposed to differ actually collapse onto the same config."""
        resolved_tuples = [row["resolved"] for row in _PERSISTENCE_TIMING_SCENARIOS]
        assert len(resolved_tuples) == len(set(resolved_tuples))
