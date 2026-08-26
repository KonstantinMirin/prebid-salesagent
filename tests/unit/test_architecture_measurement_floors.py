"""Floors under the measurement counters that can silently measure nothing.

Plan Decision 5 (#1858): "Each measurement stage degrades to 'measured less'
without failing. Every counter gets a minimum that fails the run when
measurement disappears."

Two floors live here. Both guard a counter whose failure mode is SILENCE — the
thing being counted disappears and the count keeps reporting success.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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
# 14 wired rows; `ENV_ROUTES +=` appends 5 more from `_UC_BUCKET_ROUTES` at
# import time. "How many wired rows are there" therefore has two answers (14 and
# 19), and a floor that does not say which it means is itself an ambiguous
# counter. This pins the runtime set — what actually routes scenarios.
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
        "UC-GET-PRODUCTS",
        # literal ENV_ROUTES block
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
        "uc011-list",
        "uc011-sync",
        "uc018-list",
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
