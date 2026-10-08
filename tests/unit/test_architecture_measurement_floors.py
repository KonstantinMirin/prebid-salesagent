"""Floors under the measurement counters that can silently measure nothing.

Plan Decision 5 (#1858): "Each measurement stage degrades to 'measured less'
without failing. Every counter gets a minimum that fails the run when
measurement disappears."

Two floors live here. Both guard a counter whose failure mode is SILENCE — the
thing being counted disappears and the count keeps reporting success.
"""

from __future__ import annotations

import ast
import configparser
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._storyboard_guard_env import ADCP_HOME, requires_pinned_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


# ── Floor 1: the BDD env-routing registry ───────────────────────────────────
#
# Deleting one row turns its scenarios dormant and every structural guard stays
# green, because the guards check the registry's SHAPE, not its MEMBERSHIP.
#
# Pinned as a SET, not a count: a count is satisfied by add-plus-drop, which is
# the same weakness this epic's suite comparisons avoid by comparing xpassed
# node ids by identity rather than by size.
#
# The set spans BOTH sources, deliberately. The literal `ENV_ROUTES` block holds
# 31 wired tags; `ENV_ROUTES +=` then appends the UC-010 dormancy rows (all
# xfailing) and 6 more wired ones from `_UC_BUCKET_ROUTES` at import time. "How
# many wired tags are there" therefore has two answers (31 and 37), and a floor
# that does not say which it means is itself an ambiguous counter. This pins the
# runtime set — what actually routes scenarios.
#
# Discipline, matching EXPECTED_LEDGER in test_storyboard_ledger_state.py:
# graduating a placeholder to wired ADDS a tag here in the same change, as a
# reviewed edit. A tag disappearing without one is the regression this catches.
EXPECTED_WIRED_ROUTES: frozenset[str] = frozenset(
    {
        # bucket rows, appended from _UC_BUCKET_ROUTES
        "ADMIN",
        "COMPAT",
        "UC-005",
        "UC-019",
        # UC-026 was disconnected in two places at once: no ENV_ROUTES row, and its
        # step module unregistered, so all 75 scenarios graded nothing while the file
        # was still being maintained. Both are connected now, which is a graduation
        # and so belongs in this pin -- deleting the row again would silently
        # dormant every one of those scenarios.
        "UC-026",
        "UC-GET-PRODUCTS",
        # literal ENV_ROUTES block
        "codes-declared-code-reaches-buyer",
        # The context echo, graded on every outcome across all four transports. Three routes.
        # Two because the scenarios need both a read tool and a write tool: a schema rejection
        # and a seller's own refusal do not both reach the buyer from one tool.
        "ctxecho-media-buys",
        "ctxecho-products",
        # The third is a different OBLIGATION, not a third tool for the same one. Those two
        # grade the ENVELOPE's context, which one seam reads off the request root and writes
        # onto the response root. AdCP declares the same opaque object on models nested INSIDE
        # a response (Package, and likewise MediaBuy, PackageUpdate, Results,
        # MediaBuyDeliveryWebhookResult), where no seam can reach it -- the boundary has no
        # notion of a collection -- so an element echo is carried by whoever builds the
        # element. create_media_buy is the cheapest request-element -> response-element pair.
        "ctxecho-packages",
        "predispatch",
        # The two tenant-identification routes this deployment answers on (Host and
        # x-adcp-tenant), graded through the public capabilities tool. Pinned in the
        # change that registered the route: before it, NO test set a virtual_host, so
        # the host branch had never executed anywhere.
        # The agent card is a root endpoint, not a registry tool, so its scenarios reach it
        # through `env.fetch_agent_card` rather than `call_via`.
        "agentcard",
        "tenantid",
        # A publisher's adagents.json naming this agent, graded through the three admin
        # actions that read it. Pinned in the change that registered the route.
        "pubauth",
        # BR-PROTOCOL-001: inbound version negotiation, graded on a tool that is not
        # get_adcp_capabilities. Pinned in the same change that registered the route.
        "protocol-version-negotiation",
        "egress-create",
        "egress-get-products",
        "egress-sync",
        "egress-sync-creds",
        "egress-update",
        "get-products-pricing-options",
        # The pricing row's sibling: BR-UC-GET-PRODUCTS-format-options stores real
        # products.format_options documents and reads them off get_products. Pinned on the
        # same reasoning as every other wired row, and with a concrete history behind it --
        # the scenarios were dormant on their first run ("No harness wired for None", twelve
        # auto-xfails in under a second) because a scenario carrying its own identity tag is
        # claimed by no coarse uc bucket. Deleting this row returns them to exactly that.
        "get-products-format-options",
        "security-wire-error-safety",
        "security-tenant-isolation",
        "database-fail-fast",
        "uc002-account",
        "uc002-ext",
        "uc002-idempotency",
        "uc002-manual-approval",
        "uc003-ext",
        "uc003-manual-approval",
        "uc003-storyboard-generic-client",
        "uc004-circuit-breaker",
        "uc004-create",
        "uc004-poll",
        "uc006-creative-sync",
        # UC-010's wired row, graduated on the signing branch: it builds a real
        # `CapabilitiesEnv` (`_build_capabilities_env`) with `xfail_reason=None`
        # and routes every tag in the UC-010 wired set. The UC's placeholder rows
        # (`uc010-parked-*`, `uc010-not-wired`) stay unpinned, as placeholders
        # must.
        "uc010-capabilities",
        "uc019-post-create-poll",
        "uc011-list",
        "uc011-sync",
        "uc018-list",
        # The two former catch-all PARKS, now wired: their rows build the same env their
        # UC's other rows do and carry no xfail_reason, so every scenario of UC-011 and
        # UC-018 executes. They are pinned here for the same reason as any other wired
        # route — deleting one would silently dormant every scenario that falls through to
        # it — and an unbound step in those UCs now fails through the dormancy tripwire
        # (tests/bdd/dormant_scenarios.txt), which names the missing step, rather than
        # xfailing invisibly.
        "uc011-not-wired",
        "uc018-not-wired",
    }
)


def test_every_wired_env_route_is_still_registered() -> None:
    """A wired route disappearing must redden, not silently dormant its scenarios."""
    from tests.bdd import conftest

    wired = {route.tag for route in conftest.ENV_ROUTES if route.xfail_reason is None}
    missing = sorted(EXPECTED_WIRED_ROUTES - wired)
    added = sorted(wired - EXPECTED_WIRED_ROUTES)

    assert not missing, (
        f"{len(missing)} wired env-route(s) vanished from ENV_ROUTES: {missing}. "
        "Their scenarios are now dormant and no other guard notices. Restore the row, or — if "
        "the removal is deliberate — drop the tag from EXPECTED_WIRED_ROUTES in the same change."
    )
    assert not added, (
        f"{len(added)} wired env-route(s) are registered but not pinned: {added}. "
        "Add them to EXPECTED_WIRED_ROUTES so a later deletion is caught (graduating a "
        "placeholder to wired belongs in the same change as its pin)."
    )


# ── Floor 2: the published check-index cannot shrink unnoticed ─────────────
#
# The gate-schema oracle declares this blind spot about itself: both of its
# assertions read the PUBLISHED records, and only ON-PATH and GATED storyboards
# are published (`INDEXED_STATUSES`). A DECLARING storyboard misrouted to
# OFF-PATH therefore leaves the index entirely, and a comparison over what is
# present cannot see an absence. Measured blast radius: misrouting the 21 gated
# storyboards that carry no ledger entry drops 516 of 544 GATED records — 38% of
# the 1351-record index — and the whole 110-module architecture suite stays
# green.
#
# Pinned as a SET, not a count, for the same reason the route floor above is:
# a count is satisfied by add-plus-drop. The set is what makes a misroute
# visible, because a misrouted storyboard leaves it.
EXPECTED_GATED_STORYBOARDS: frozenset[str] = frozenset(
    {
        "protocols/media-buy/scenarios/acceptance_policy_discovery.yaml",
        "protocols/media-buy/scenarios/account_timezone_buyer_selected.yaml",
        "protocols/media-buy/scenarios/account_timezone_seller_assigned.yaml",
        "protocols/media-buy/scenarios/account_timezone_seller_fixed.yaml",
        "protocols/media-buy/scenarios/audience_activation_discovery.yaml",
        "protocols/media-buy/scenarios/audience_buy_flow.yaml",
        "protocols/media-buy/scenarios/bidding_cost_binding.yaml",
        "protocols/media-buy/scenarios/bidding_policy_placement.yaml",
        "protocols/media-buy/scenarios/budget_cap_timezone_account.yaml",
        "protocols/media-buy/scenarios/budget_cap_timezone_fixed.yaml",
        "protocols/media-buy/scenarios/budget_cap_timezone_override.yaml",
        "protocols/media-buy/scenarios/budget_cap_timezone_override_rejected.yaml",
        "protocols/media-buy/scenarios/catalog_item_availability_updates.yaml",
        "protocols/media-buy/scenarios/clicks_buy_flow.yaml",
        "protocols/media-buy/scenarios/compact_direct_buy_lifecycle.yaml",
        "protocols/media-buy/scenarios/compact_product_lifecycle.yaml",
        "protocols/media-buy/scenarios/completed_views_buy_flow.yaml",
        "protocols/media-buy/scenarios/create_media_buy_async.yaml",
        "protocols/media-buy/scenarios/create_media_buy_async_lifecycle.yaml",
        "protocols/media-buy/scenarios/creative_fate_after_cancellation.yaml",
        "protocols/media-buy/scenarios/cross_path_targeting_provenance.yaml",
        "protocols/media-buy/scenarios/declined_proposal_execution.yaml",
        "protocols/media-buy/scenarios/declined_proposal_refinement.yaml",
        "protocols/media-buy/scenarios/demographic_targeting.yaml",
        "protocols/media-buy/scenarios/dependency_impairment_audience.yaml",
        "protocols/media-buy/scenarios/event_dedup_flow.yaml",
        "protocols/media-buy/scenarios/expired_proposal_execution.yaml",
        "protocols/media-buy/scenarios/frequency_cap_capability_updates.yaml",
        "protocols/media-buy/scenarios/frequency_cap_enforcement.yaml",
        "protocols/media-buy/scenarios/geo_place_targeting.yaml",
        "protocols/media-buy/scenarios/geo_region_all_values_support.yaml",
        "protocols/media-buy/scenarios/geo_region_exclusion_support.yaml",
        "protocols/media-buy/scenarios/geo_region_targeting.yaml",
        "protocols/media-buy/scenarios/governance_agent_binding_acceptance.yaml",
        "protocols/media-buy/scenarios/inline_creatives_without_sync.yaml",
        "protocols/media-buy/scenarios/inventory_list_no_match.yaml",
        "protocols/media-buy/scenarios/inventory_list_targeting.yaml",
        "protocols/media-buy/scenarios/measurement_terms_accepted.yaml",
        "protocols/media-buy/scenarios/media_buy_frequency_cap_readback.yaml",
        "protocols/media-buy/scenarios/media_buy_frequency_cap_updates.yaml",
        "protocols/media-buy/scenarios/package_automatic_bidding.yaml",
        "protocols/media-buy/scenarios/performance_buy_flow.yaml",
        "protocols/media-buy/scenarios/performance_buy_flow_roas.yaml",
        "protocols/media-buy/scenarios/product_signal_targeting.yaml",
        "protocols/media-buy/scenarios/reach_buy_flow.yaml",
        "protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml",
        "protocols/media-buy/scenarios/refine_products.yaml",
        "protocols/media-buy/scenarios/seller_optimized_budget.yaml",
        "protocols/media-buy/scenarios/typed_proposal_negotiation.yaml",
        "protocols/media-buy/scenarios/vendor_metric_accountability.yaml",
        "protocols/media-buy/scenarios/vendor_metric_catalog_precondition.yaml",
        "protocols/media-buy/scenarios/vendor_metric_optimization_flow.yaml",
        "protocols/media-buy/state-machine.yaml",
        "universal/account-identity-reconciliation.yaml",
        "universal/get-products-pagination-integrity.yaml",
        "universal/oauth-setup.yaml",
        "universal/trusted-match-publisher-authentication.yaml",
        "universal/wholesale-feed-bulk-webhooks.yaml",
        "universal/wholesale-feed-product-webhooks.yaml",
        "universal/wholesale-feed-products-scope-isolation.yaml",
        "universal/wholesale-feed-products.yaml",
        "universal/wholesale-feed-signal-webhooks.yaml",
        "universal/wholesale-feed-signals-scope-isolation.yaml",
        "universal/wholesale-feed-signals.yaml",
    }
)

#: Floor under the record count itself. A count, not a set — the records are the
#: thing being counted, and 1303 individual ids would be a second index rather
#: than a floor. It catches wholesale collapse; the SET above catches a misroute.
#:
#: 1351 -> 1303 (salesagent-b341x.22). The 48 records that left belonged to three
#: storyboards — universal/error-compliance-signals.yaml,
#: universal/get-signals-pagination-integrity.yaml and
#: universal/schema-validation-signals.yaml — that were on-path ONLY because the
#: coverage map's hand-maintained ADVERTISED_TOOLS claimed `get_signals` and
#: `activate_signal`, which no transport registers. Deriving the set from
#: src/core/tools/registry.py took them off the path, so those 48 were never
#: gradable and were inflating the denominator every conformance number here is
#: quoted against. Lowering a floor is normally the thing this file exists to
#: prevent; it is correct here because the drop was MEASURED and its cause named,
#: which is the same discipline EXPECTED_GATED_STORYBOARDS above states for a
#: deliberate reclassification.
#:
#: 1303 -> 3166 AT THE 3.2.1 PIN, RAISED not lowered. The 3.2.1 compliance tree publishes
#: far more graded material than 3.1.1 did, and leaving the floor at 1303 would have let a
#: collapse from 3166 to 1400 pass unnoticed -- the exact failure this floor exists to
#: catch. Measured from the built index, not estimated.
#:
#: EXPECTED_GATED_STORYBOARDS moved with it, and the direction of every change was checked
#: before re-pinning rather than after: FIVE left the GATED set by being PROMOTED to
#: ON-PATH (available_actions, dependency_impairment, dependency_impairment_cardinality,
#: pending_creatives_to_start, per_creative_conversion_attribution -- each now reports
#: ON-PATH in the built index), which is the deliberate-reclassification case the guard
#: names and NOT the misroute case, because their checks are still published where the
#: gate-schema oracle can read them. FORTY-FOUR arrived gated with the pin.
MINIMUM_INDEX_CHECKS = 3166


@requires_pinned_bundle
def test_the_published_check_index_does_not_silently_shrink() -> None:
    """A declaring storyboard leaving the index must redden, not go quiet."""
    from scripts.audit import storyboard_check_index

    index = storyboard_check_index.build(REPO_ROOT, ADCP_HOME)
    gated = {r["storyboard"] for r in index["records"] if r["gate"] == "GATED"}

    missing = sorted(EXPECTED_GATED_STORYBOARDS - gated)
    added = sorted(gated - EXPECTED_GATED_STORYBOARDS)

    assert not missing, (
        f"{len(missing)} GATED storyboard(s) left the published index: {missing}. "
        "Either the gate classifier misrouted them to OFF-PATH — in which case their checks "
        "vanished from the index and the gate-schema oracle cannot see the absence — or the "
        "reclassification is deliberate and belongs in EXPECTED_GATED_STORYBOARDS in the same change."
    )
    assert not added, (
        f"{len(added)} GATED storyboard(s) are published but not pinned: {added}. "
        "Add them so a later disappearance is caught."
    )
    assert index["totals"]["checks"] >= MINIMUM_INDEX_CHECKS, (
        f"the check index published {index['totals']['checks']} records, below the "
        f"{MINIMUM_INDEX_CHECKS} floor. The index is the denominator every conformance "
        "number here is quoted against; it shrinking silently makes every one of them flattering."
    )


# ── Floor 2: the liveness artifact's collect-only protection ────────────────
#
# `scenario_liveness.pytest_sessionfinish` returns early on a collect-only
# session. Without it, `make quality` destroys the artifact on every run: it
# shells out to `pytest tests/bdd --collect-only`, whose empty `_RECORDS` would
# be written as `{"scenarios": []}`, and the join fails CLOSED on an empty file
# — so every check silently reports liveness 0.
#
# The step body records that two independent mutations removed this branch and
# every guard stayed green. This is the test that was missing.


def test_collect_only_session_does_not_write_the_liveness_artifact(tmp_path, monkeypatch) -> None:
    """A session that observed nothing must not overwrite a real artifact."""
    from tests.bdd import scenario_liveness

    artifact = tmp_path / "liveness.json"
    artifact.write_text('{"scenarios": [{"scenario_id": "real"}]}', encoding="utf-8")
    monkeypatch.setenv("BDD_LIVENESS_ARTIFACT", str(artifact))

    # NO `workeroutput` attribute: `_is_xdist_worker` is `hasattr(config,
    # "workeroutput")`, so supplying one sends this down the WORKER branch,
    # which returns before the collect-only check is ever reached. A first
    # version of this test did exactly that — it passed with the collect-only
    # branch deleted, i.e. it asserted nothing. The mutation caught it.
    session = SimpleNamespace(config=SimpleNamespace(option=SimpleNamespace(collectonly=True)))
    assert not scenario_liveness._is_xdist_worker(session.config), (
        "this session must take the CONTROLLER path or the test is vacuous"
    )
    scenario_liveness.pytest_sessionfinish(session)

    assert artifact.read_text(encoding="utf-8") == '{"scenarios": [{"scenario_id": "real"}]}', (
        "a collect-only session overwrote the liveness artifact — the branch in "
        "scenario_liveness.pytest_sessionfinish that returns early on collectonly is gone or "
        "no longer reached, and `make quality` will now destroy the artifact on every run"
    )


# ── Floor 3: a narrowed bdd run must not pass as a measurement ──────────────
#
# The collect-only return closes the ZERO case. NARROWING was the remaining
# hole: seeding the artifact with 900 records and running
# `pytest tests/bdd -k "storyboard and recancel"` rewrote it to ONE record, and
# the other 899 read as dormant — a claim about production, from a file that
# only recorded a narrower question having been asked.


def test_a_narrowed_run_is_rejected_rather_than_read_as_dormancy(tmp_path) -> None:
    """The artifact's own scope block must make a partial run visible."""
    from scripts.audit import scenario_liveness_join, storyboard_spec

    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps(
            {
                "run": {"collected": 1, "selection": "storyboard and recancel", "markers": ""},
                "scenarios": [{"scenario_id": "T-UC-003-x", "steps_bound": True, "ledgered": False}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(storyboard_spec.StoryboardAuditError) as excinfo:
        scenario_liveness_join.load_artifact(artifact)
    assert "storyboard and recancel" in str(excinfo.value)


@pytest.mark.parametrize("args", [["tests/bdd"], ["tests"], ["."], ["tests/bdd", "tests/bdd"]])
def test_a_full_run_is_still_read_normally(tmp_path, args) -> None:
    """The floor must not reject the artifact it exists to protect.

    The suite root and every ancestor of it collect the whole suite on the way
    past, so all of these asked the whole question.
    """
    from scripts.audit import scenario_liveness_join

    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps(
            {
                "run": {
                    "collected": 900,
                    "args": args,
                    "suite": "tests/bdd",
                    "selection": "",
                    "markers": "",
                },
                "scenarios": [{"scenario_id": "T-UC-003-x", "steps_bound": True, "ledgered": False}],
            }
        ),
        encoding="utf-8",
    )

    assert set(scenario_liveness_join.load_artifact(artifact)) == {"T-UC-003-x"}


# ── Floor 4: narrowing by PATH sets no -k and no -m ─────────────────────────
#
# Floor 3 watched `-k`/`-m` and nothing else, which is the narrowing nobody
# here uses. `pytest tests/bdd/test_uc010_discover_seller_capabilities.py`
# records neither expression, so a 24-record artifact over a suite of some
# eight thousand parametrized scenarios was accepted as a full measurement and
# every scenario it did not name read as dormant — the exact
# claim-about-production Floor 3 exists to refuse, through the door it did not
# watch (salesagent-peq79).
#
# MEASURED, three artifacts inside half an hour in one shared worktree:
#   07:27  selection='daily_breakdown'               30 collected -> refused
#   07:41  selection='', one module by path          24 collected -> ACCEPTED
#   07:50  selection='creative_missing_required_url'  3 collected -> refused
# A full tests/unit run spanning 07:42-07:53 read the 07:41 file and PASSED
# test_the_published_check_index_does_not_silently_shrink; two minutes later it
# reads the 07:50 one and fails. The guard's own verdict was a coin flip on
# which narrowed run wrote last.


@pytest.mark.parametrize(
    "args",
    [
        ["tests/bdd/test_uc010_discover_seller_capabilities.py"],
        ["tests/bdd/test_uc010_discover_seller_capabilities.py", "tests/bdd/test_uc010_declaration_backing.py"],
        ["tests/bdd"],  # one whole-suite arg does not license the narrow one beside it
        ["tests/bdd-extra"],  # a sibling whose name merely starts with the suite's
    ],
)
def test_a_path_narrowed_run_is_rejected_though_it_records_no_k_or_m(tmp_path, args) -> None:
    """A run narrowed by path must be refused on its own recorded scope."""
    from scripts.audit import scenario_liveness_join, storyboard_spec

    narrow = "tests/bdd/test_uc010_discover_seller_capabilities.py"
    if narrow not in args:
        args = [*args, narrow]

    artifact = tmp_path / "liveness.json"
    artifact.write_text(
        json.dumps(
            {
                # The 07:41 artifact's own numbers: no -k, no -m, 24 records.
                "run": {
                    "collected": 24,
                    "args": args,
                    "suite": "tests/bdd",
                    "selection": "",
                    "markers": "",
                },
                "scenarios": [{"scenario_id": "T-UC-010-x", "steps_bound": True, "ledgered": False}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(storyboard_spec.StoryboardAuditError) as excinfo:
        scenario_liveness_join.load_artifact(artifact)
    assert narrow in str(excinfo.value), (
        "the refusal must NAME the path that narrowed the run, or the next reader cannot "
        f"tell which question was actually asked: {excinfo.value}"
    )


def test_the_writer_records_the_paths_the_reader_judges(tmp_path) -> None:
    """The two halves must agree on the field names, or the floor is unreachable.

    ``_run_scope`` and ``_reject_narrowed_run`` live in different trees
    (``tests/bdd`` and ``scripts/audit``), so nothing but this test fails when one
    renames a key. Without it the guard degrades silently to the legacy
    allow-through path, which is indistinguishable from passing.
    """
    from scripts.audit import scenario_liveness_join, storyboard_spec
    from tests.bdd import scenario_liveness

    repo_root = Path(__file__).resolve().parents[2]
    session = SimpleNamespace(
        testscollected=24,
        exitstatus=0,
        testsfailed=0,
        deselected=(),
        config=SimpleNamespace(
            option=SimpleNamespace(keyword="", markexpr=""),
            rootpath=repo_root,
            args=["tests/bdd/test_uc010_discover_seller_capabilities.py"],
            invocation_params=SimpleNamespace(dir=repo_root),
        ),
    )
    scope = scenario_liveness._run_scope(session)

    assert scope["suite"] == "tests/bdd", f"the writer no longer locates its own suite: {scope}"
    assert scope["args"] == ["tests/bdd/test_uc010_discover_seller_capabilities.py"], (
        f"the writer no longer records the paths it was asked to collect: {scope}"
    )

    artifact = tmp_path / "liveness.json"
    artifact.write_text(json.dumps({"run": scope, "scenarios": []}), encoding="utf-8")
    with pytest.raises(storyboard_spec.StoryboardAuditError):
        scenario_liveness_join.load_artifact(artifact)


# ── Floor 5: a suite-wide bdd env must not write a path another env reads ───
#
# The artifact's integrity does not only depend on the reader refusing a
# narrowed run (Floors 3-4). It also depends on nobody CLOBBERING the file
# mid-read, and that was a tox.ini asymmetry: `BDD_PAYLOAD_ARTIFACT` was
# scoped to {toxworkdir} for all three bdd envs while `BDD_LIVENESS_ARTIFACT`
# was scoped for bdd_e2e alone, so `bdd` and `bdd_inprocess` fell through to
# the cwd-relative default that the `unit` env READS. Neither `unit` nor
# `quality` declares `depends`, so under `tox -p` writer and readers run in
# the same wave. Fixed by scoping both; this guard is what stops the next
# bdd-ish env from reintroducing it (salesagent-peq79).
#
# DERIVED, NOT SPELLED, in two directions — a guard that listed `bdd`,
# `bdd_inprocess`, `bdd_e2e` would be the same object as the declaration it
# replaces, and the next env would be invisible to it:
#
#   * the ENV LIST comes from what each env COLLECTS (an argument naming the
#     bdd suite directory), so a new env is caught by behaving like one
#     rather than by being named like one;
#   * the VARIABLE NAMES come from the modules that own them —
#     `storyboard_spec.ARTIFACT_ENV_VAR` and `payload_capture.ARTIFACT_ENV_VAR`.
#     The two do not share a convention (`BDD_LIVENESS_ARTIFACT` is plural-less
#     and `BDD_PAYLOAD_ARTIFACT` is singular; `BDD_PAYLOADS_ARTIFACT` is read by
#     nothing and cost one lane a dozen no-op redirects), so a hardcoded string
#     here could be the wrong one and nothing would say so.


def _tox_sections() -> configparser.ConfigParser:
    """tox.ini parsed as plain config. Substitutions are left unexpanded.

    Presence of a KEY is all this floor asks about, and no tox invocation is
    needed to answer that — the same reason the CI shard manifest guard reads
    its workflow as YAML rather than running it.
    """
    parsed = configparser.ConfigParser(interpolation=None, strict=False)
    parsed.read(Path(__file__).resolve().parents[2] / "tox.ini", encoding="utf-8")
    return parsed


def _setenv_keys(parsed: configparser.ConfigParser, section: str) -> set[str]:
    """The env-var names *section* sets, plus those it inherits from ``[testenv]``.

    The base is included so hoisting a variable into ``[testenv]`` is a
    refactor this floor accepts rather than a failure it invents.
    """
    keys: set[str] = set()
    for name in ("testenv", section):
        if not parsed.has_section(name) and name != "testenv":
            continue
        for line in (parsed[name].get("setenv", "") or "").splitlines():
            if "=" in line:
                keys.add(line.split("=", 1)[0].strip())
    return keys


def _collects_the_bdd_suite(commands: str) -> bool:
    """Whether *commands* collect the bdd suite DIRECTORY, not a file inside it.

    An env that names individual modules is narrower than the suite, and the
    reader refuses its artifact anyway (Floor 4) — so it is not what this floor
    is about. Compared per whitespace-separated argument so that naming the
    directory AND a module does not read as naming only the directory.
    """
    suite = {"tests/bdd", "tests/bdd/"}
    return any(arg in suite for arg in commands.split())


def test_every_env_that_runs_the_bdd_suite_scopes_both_artifacts() -> None:
    """A suite-wide bdd env must write both artifacts somewhere private to it."""
    from scripts.audit.storyboard_spec import ARTIFACT_ENV_VAR as LIVENESS_VAR
    from tests.bdd.payload_capture import ARTIFACT_ENV_VAR as PAYLOAD_VAR

    parsed = _tox_sections()
    suite_envs = [
        section
        for section in parsed.sections()
        if section.startswith("testenv:") and _collects_the_bdd_suite(parsed[section].get("commands", "") or "")
    ]
    assert suite_envs, (
        "no tox env appears to collect the bdd suite directory — the derivation above has "
        "stopped matching how tox.ini spells its commands, so this floor is grading nothing"
    )

    unscoped = {section: sorted({LIVENESS_VAR, PAYLOAD_VAR} - _setenv_keys(parsed, section)) for section in suite_envs}
    offenders = {section: missing for section, missing in unscoped.items() if missing}
    assert not offenders, (
        f"these tox envs run the whole bdd suite without scoping {sorted({LIVENESS_VAR, PAYLOAD_VAR})}: "
        f"{offenders}. Unscoped, the artifact lands at its cwd-relative default under "
        "test-results/, which is the path the `unit` env reads — and `unit` declares no "
        "`depends`, so under `tox -p` this env writes the file while the unit suite reads it. "
        "Set it to a {toxworkdir} path, as the other bdd envs do."
    )


# ── Floor 6: a test that spawns pytest over bdd must redirect both artifacts ─
#
# THE THIRD DOOR. Floors 3-4 made the reader refuse a narrowed artifact and
# Floor 5 stopped two tox envs sharing the path, and neither touched the writer
# that was actually doing it: `test_payload_capture_xdist.py` spawns a nested
# pytest over three bdd modules (9 collected), redirected the PAYLOAD artifact
# it reads, and let the LIVENESS one land at the cwd-relative test-results/
# default. That is the artifact two full runs' guards refused as "narrowed BY
# PATH" — the refusal was right and the writer was a test (salesagent-peq79).
#
# Floor 5's population could not see it: that floor derives over `tox.ini`
# envs, and this writer is a subprocess spawned from the `integration` env,
# which sets no override to inherit. A derivation whose population excludes the
# case it exists for is worse than a declaration, because a declaration would
# at least have been visibly incomplete.
#
# THE PAIR WERE EXACT MIRRORS, which is the finding rather than a detail:
# `test_payload_capture_xdist.py` redirected the payload artifact and leaked
# the liveness one; `test_bdd_scenario_liveness_real_run.py` redirected the
# liveness artifact and leaked the payload one. Each redirected what it LOOKED
# AT and leaked what it did not, so neither author was careless — the rule
# "redirect the artifact you assert on" produces this. The rule has to be
# "redirect every artifact the nested run WRITES".
#
# COLLECT-ONLY IS NOT IN THE POPULATION, and that is derived too rather than
# assumed: `scenario_liveness.pytest_sessionfinish` returns early on
# `collectonly` (Floor 2), so such a session writes no artifact and has nothing
# to redirect.


_BDD_ARTIFACT_WRITERS_HINT = "tests/bdd/"


def _bdd_path_constants(tree: ast.AST) -> list[str]:
    """Path-shaped string constants naming the bdd suite.

    A CONSTANT, so comments are invisible to this (they are absent from the AST),
    and ``startswith`` so a prose mention inside a docstring -- "the ledger at
    tests/bdd/e2e_rest_known_failures.txt" -- is not mistaken for an argument.
    Three files mention a bdd path only in prose and are correctly excluded.
    """
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(_BDD_ARTIFACT_WRITERS_HINT)
    ]


def _spawns_a_real_pytest(tree: ast.AST) -> bool:
    """Whether some call's first argument is a pytest argv that actually RUNS tests."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        argv = [
            arg.value for arg in ast.walk(node.args[0]) if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        if "pytest" in argv and not any(a.startswith("--collect-only") or a == "--co" for a in argv):
            return True
    return False


def test_a_test_that_runs_the_bdd_suite_redirects_every_artifact_it_writes() -> None:
    """A nested bdd run must not emit an artifact into a path something else grades."""
    from scripts.audit.storyboard_spec import ARTIFACT_ENV_VAR as LIVENESS_VAR
    from tests.bdd.payload_capture import ARTIFACT_ENV_VAR as PAYLOAD_VAR

    tests_root = Path(__file__).resolve().parents[1]
    writers: dict[Path, list[str]] = {}
    for source in sorted(tests_root.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        if _bdd_path_constants(tree) and _spawns_a_real_pytest(tree):
            body = source.read_text(encoding="utf-8")
            writers[source] = sorted(
                {LIVENESS_VAR, PAYLOAD_VAR} - {v for v in (LIVENESS_VAR, PAYLOAD_VAR) if v in body}
            )

    assert writers, (
        "no test appears to spawn a real pytest over a bdd path — the derivation above has "
        "stopped matching how these tests are written, so this floor is grading nothing"
    )
    leaking = {str(path.relative_to(tests_root)): missing for path, missing in writers.items() if missing}
    assert not leaking, (
        f"these tests spawn a nested pytest over the bdd suite without redirecting every "
        f"artifact that run writes: {leaking}. Unredirected, the artifact lands at its "
        "cwd-relative default under test-results/ — the liveness one is read by thirteen "
        "storyboard guards, which then refuse it as a narrowed run. Point each at tmp_path, "
        "as the other bdd-spawning tests do."
    )
