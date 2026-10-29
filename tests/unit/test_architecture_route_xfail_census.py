"""Ratchet: the population of BDD scenarios xfailed at FIXTURE SETUP may only shrink.

``tests/bdd/conftest.py::_run_env_route`` begins

    if route.xfail_reason is not None:
        pytest.xfail(route.xfail_reason)

so an ``EnvRoute`` row carrying a reason xfails the scenario before its env is built and
before one step runs. The scenario is still bound, still collected, and still counted by
every guard that counts scenarios -- and it grades nothing.

That is a fifth routing mechanism, and the one with no baseline. The other four are
auditable by reading a file: a conftest xfail tag set, ``dormant_scenarios.txt``,
``e2e_rest_known_failures.txt``, a ``pytest.mark``. This one is a ``when=`` predicate on a
registry row, and the three largest rows are ``lambda m: True`` catch-alls -- they claim
every scenario of their UC that no earlier row took, so a scenario can join the population
by being WRITTEN, with no edit to any list. Measured when this guard landed: 819 of 2879
routed combinations, 28%.

WHY A RATCHET AND NOT A REFUSAL, which is the opposite of the sibling decision.
``test_architecture_bdd_unrouted_is_refused`` refuses its mechanism outright because its
population is ZERO, and a zero-entry baseline is only something to grow. Here the
population is 819 and every row names a real unfinished harness, so refusing would delete
work rather than measure it. A shrink-only count is what fits a non-empty population that
should drain.

WHAT THIS GUARD DOES NOT CLAIM. It does not say these scenarios SHOULD xfail, and it does
not grade the reason strings -- ``test_architecture_uc010_dormancy_citations`` already
grades that each UC-010 dormant tag's reason cites its own issue, and
``test_architecture_bdd_ext_fallback_xfail`` already grades that each ext-split UC HAS a
not-wired row. Those two protect the rows' CONTENT and EXISTENCE. Nothing protected their
SIZE, which is all this adds.

TRANSPORT-INDEPENDENT BY CONSTRUCTION. The item count depends on ``BDD_E2E_ENABLED``: the
same scenarios collect on three in-process transports or on four
(salesagent-8qela.151), so 819 combinations are 2457 items or 3276 depending on a flag no
guard controls. This counts the combination -- the nodeid with its transport
parametrization removed -- which is identical either way.

DERIVED, NEVER DECLARED, AND FROM ONE COLLECTION. The rows come from
``collect_bdd_items_with_markers`` -- the SAME nested collection
``test_architecture_env_route_agreement`` grades on, which already carries its own
truncation floor and emits each item's marker set through the pinned accessor. The verdict
per row comes from the PRODUCTION resolver, ``storyboard_spec.resolve_env_route`` over the
live ``ENV_ROUTES``. A hand-written list of UCs, or a second collector, would be a second
derivation and would drift from the routing it claims to describe.

WHY THIS IS NOT A ``RatchetCounter``. ``test_architecture_ratchet_enforcement`` requires
every registered ratchet to name an enforcement that actually runs, because a ratchet filed
only under ``stages: [pre-push]`` fires nowhere in this workflow. Its own message names the
two acceptable homes: "'guard' (a test in the always-run unit suite)" or "'gate' (the
quality tox env)". This is the first -- it runs on every unit-suite invocation, in ~13s --
so it needs no ``.pre-commit-coverage-map.yml`` entry and no committed baseline file. The
counters registered there are line-counting hooks over source text; this one derives its
population from a collection, which is a different shape with the same discipline.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.unit._architecture_helpers import (
    assert_violations_match_allowlist,
    collect_bdd_items_with_markers,
)

#: Per-route ceiling on routed (function, non-transport-parametrization) combinations.
#:
#: SHRINK-ONLY. Wiring a harness LOWERS an entry in the same change, as a reviewed edit;
#: a row whose count rises is a scenario that joined a catch-all, which is the regression
#: this file exists to catch. Raising an entry is never the fix.
#:
#: A row ABSENT here is a row that must not exist: a new ``xfail_reason`` route fails
#: :func:`test_every_setup_xfail_route_is_declared` until it is added deliberately, which
#: is the door the catch-alls left open.
#:
#: Measured at integrate/sdk9-lanes b6e2554c5 by this file's own derivation.
_CEILINGS: dict[str, int] = {
    # The three catch-alls: `when=_uc("UC-00n", lambda m: True)`. They claim every
    # scenario of their UC that no earlier row took, so these are the entries that can
    # grow without anyone editing a list. 804 of the 819.
    # 395 -> 385: twelve create-time billing combinations deleted (create_media_buy has no
    # billing field at the pin), plus two added by corrections -- inv-080-11 became an
    # outline over rejected and closed, and the tasks-sort-field partition gained the
    # "domain is not a sort field" row.
    "uc002-not-wired": 385,
    "uc003-not-wired": 381,
    "uc010-not-wired": 28,
    # Per-tag UC-010 dormancy rows, generated from `_UC010_PARKED_TAGS`. Their reasons
    # cite issues and `test_architecture_uc010_dormancy_citations` grades the citation;
    # only the size was uncounted.
    "uc010-dormant-T-UC-010-v31-identity-key-origins": 4,
    "uc010-dormant-T-UC-010-v31-governance-aware": 2,
    "uc010-dormant-T-UC-010-v31-creative-multiplicity": 1,
    "uc010-dormant-T-UC-010-v31-vendor-metric-optimization": 1,
    "uc010-dormant-T-UC-010-v31-creative-specs": 1,
    "uc010-dormant-T-UC-010-v31-identity-compromise-notification": 1,
    "uc010-dormant-T-UC-010-v31-content-standards-block": 1,
    "uc010-dormant-T-UC-010-v31-identity-brand-json-url": 1,
    "uc010-dormant-T-UC-010-v31-creative-extended": 1,
    "uc010-dormant-T-UC-010-v31-creative-agentic-flags": 1,
}

#: The population floor. A derivation that matches nothing is silently green, and that is
#: this family's failure mode -- so a census that finds almost nothing fails rather than
#: reporting a clean pass. Deliberately far below the measured 819: this catches a BROKEN
#: DERIVATION, it does not pin the count, which ``_CEILINGS`` does per row.
_MIN_ROUTED_COMBINATIONS = 400

_TRANSPORTS = ("mcp", "a2a", "rest", "e2e_rest", "e2e_mcp", "e2e_a2a", "e2e_admin")

_BRACKET = re.compile(r"\[(?P<params>.*)\]$")


def _combination(nodeid: str) -> str:
    """The nodeid with its transport parametrization removed.

    pytest-bdd parametrizes the transport FIRST inside the bracket, so dropping a leading
    ``<transport>-`` leaves the scenario's own parametrization intact. Only a known
    transport is stripped: a blind ``partition("-")`` would eat the first token of any
    scenario whose own parameter happens to lead, and silently merge distinct rows.
    """
    match = _BRACKET.search(nodeid)
    if match is None:
        return nodeid
    head, params = nodeid[: match.start()], match.group("params")
    for transport in _TRANSPORTS:
        if params == transport:
            return head
        if params.startswith(f"{transport}-"):
            return f"{head}[{params[len(transport) + 1 :]}]"
    return nodeid


class _Census:
    """The partition of the collected suite by routing verdict."""

    def __init__(self, rows: tuple[dict[str, Any], ...]) -> None:
        from scripts.audit import storyboard_spec
        from tests.bdd.conftest import ENV_ROUTES

        self.collected = len(rows)
        self.wired = 0
        self.unrouted = 0
        self.combinations: dict[str, set[str]] = {}
        self.items: Counter[str] = Counter()
        for row in rows:
            names = frozenset(row["derived"] or row["markers"])
            route = storyboard_spec.resolve_env_route(names, ENV_ROUTES)
            if route is None:
                self.unrouted += 1
            elif route.xfail_reason is None:
                self.wired += 1
            else:
                self.combinations.setdefault(route.tag, set()).add(_combination(row["nodeid"]))
                self.items[route.tag] += 1

    @property
    def routed_combinations(self) -> int:
        return sum(len(combos) for combos in self.combinations.values())


@pytest.fixture(scope="module")
def census() -> _Census:
    return _Census(collect_bdd_items_with_markers())


@pytest.mark.arch_guard
def test_the_census_accounts_for_every_collected_item(census: _Census) -> None:
    """The partition is exhaustive, and it found a real population.

    Both halves matter. Without the floor, a derivation matching nothing satisfies every
    ceiling below. Without the partition, an item the resolver answered for in some third
    way would leave the arithmetic unnoticed.
    """
    accounted = census.wired + census.unrouted + sum(census.items.values())
    assert accounted == census.collected, (
        f"the partition accounts for {accounted} of {census.collected} collected items: "
        "wired + unrouted + setup-xfailed must be the whole collection"
    )
    assert census.routed_combinations >= _MIN_ROUTED_COMBINATIONS, (
        f"only {census.routed_combinations} routed combinations were found (expected at "
        f"least {_MIN_ROUTED_COMBINATIONS}); the resolver, the marker accessor or "
        "ENV_ROUTES changed shape and this census is grading nothing"
    )


@pytest.mark.arch_guard
def test_no_setup_xfail_route_grows(census: _Census) -> None:
    """Every route's routed-combination count is at or below its ceiling."""
    grown = {
        tag: (len(combos), _CEILINGS[tag])
        for tag, combos in sorted(census.combinations.items())
        if tag in _CEILINGS and len(combos) > _CEILINGS[tag]
    }
    assert not grown, (
        "setup-phase xfail routes grew. Those scenarios are bound, collected and counted, "
        "and they grade nothing -- wire the harness or move the scenario; do not raise the "
        f"ceiling: {grown}"
    )


@pytest.mark.arch_guard
def test_the_declared_routes_are_exactly_the_routed_ones(census: _Census) -> None:
    """``_CEILINGS``' key set must EQUAL the set of routes that xfail at setup.

    Two obligations in one equality, which is why this is the shared primitive's shape
    rather than two hand-rolled set differences:

    * a route present and UNDECLARED is a new placeholder row carrying any number of
      scenarios while the ceilings say nothing about it -- the catch-all door;
    * a route declared and ABSENT is a stale entry. Draining to zero is the GOAL, so a
      route that drains loses its entry in the same change, or this file accumulates
      ceilings nobody can grow and the next reader cannot tell which are live.

    ``assert_violations_match_allowlist`` reports those two separately, as "new violations"
    and "stale entries" -- exactly the distinction, reported the way every other allowlist
    in the suite reports it.
    """
    assert_violations_match_allowlist(
        {(tag,) for tag in census.combinations},
        {(tag,) for tag in _CEILINGS},
        fix_hint=(
            "A newly routed row needs a ceiling entry with its measured count, or should "
            "not exist. A stale entry means the harness was wired -- delete it, the work is "
            "done. The per-route COUNT is graded separately by "
            "test_no_setup_xfail_route_grows: a shrink-only numeric ceiling, which is not a "
            "set comparison and so is not expressible here."
        ),
    )


@pytest.mark.arch_guard
def test_the_combination_key_strips_the_transport_and_nothing_else() -> None:
    """``_combination`` is what makes the ceilings independent of ``BDD_E2E_ENABLED``.

    Both directions, because a key stripping too much merges distinct scenarios and
    under-counts, and one stripping too little counts a scenario once per transport and
    makes every ceiling depend on a flag no guard controls (salesagent-8qela.151).
    """
    node = "tests/bdd/test_uc003_update_media_buy.py::test_x"
    assert {
        _combination(f"{node}[{transport}-case_a-expected]") for transport in ("mcp", "a2a", "rest", "e2e_rest")
    } == {f"{node}[case_a-expected]"}
    assert _combination(f"{node}[mcp]") == node
    assert _combination(f"{node}[mcp-case_a]") != _combination(f"{node}[mcp-case_b]")
    assert _combination(node) == node
    # A parameter that merely LOOKS like a lead token is left alone: only a known
    # transport is stripped, so this scenario keeps both of its own parameters.
    assert _combination(f"{node}[restaurant-case_a]") == f"{node}[restaurant-case_a]"


@pytest.mark.arch_guard
def test_the_census_reads_the_production_routing_call() -> None:
    """The names this guard derives from are the ones the BDD conftest routes on.

    If ``_harness_env`` stopped calling ``resolve_env_route``, or stopped keying it on
    ``derive_marker_names``, or stopped xfailing on a reason, this census would still
    answer -- about a function nothing uses. A guard measuring a path production no longer
    takes is the defect salesagent-8qela.14 was filed about one level down, so the three
    lines it depends on are asserted rather than assumed.
    """
    source = (Path(__file__).resolve().parents[1] / "bdd" / "conftest.py").read_text(encoding="utf-8")
    for line in (
        "marker_names = derive_marker_names(request.node)",
        "storyboard_spec.resolve_env_route(marker_names, ENV_ROUTES)",
        "pytest.xfail(route.xfail_reason)",
    ):
        assert line in source, f"the production routing call changed shape: {line!r} is gone"
