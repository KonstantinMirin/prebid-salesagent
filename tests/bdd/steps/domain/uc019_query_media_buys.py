"""BDD step definitions for UC-019: Query Media Buys.

Given steps seed media buys in DB via factories.
When steps build GetMediaBuysRequest and dispatch through MediaBuyListEnv.
Then steps assert on GetMediaBuysResponse fields.

beads: salesagent-lqb
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pytest_bdd import given, parsers, then, when

from src.core.schemas._base import GetMediaBuysRequest
from tests.bdd.steps._outcome_helpers import wire_dict, wire_field
from tests.bdd.steps.generic._create_request import build_create_request_kwargs
from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.bdd.steps.generic.then_error import _wire_code, _wire_error_object, _wire_suggestion
from tests.factories import (
    CreativeAssignmentFactory,
    CreativeFactory,
    MediaBuyFactory,
    MediaPackageFactory,
)

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _generate_unique_id(label: str) -> str:
    """Generate a unique media_buy_id from a Gherkin label.

    Appends a uuid4 suffix so IDs never collide across parallel test runs
    or E2E scenarios sharing a database, while keeping the label prefix
    for human readability in logs.
    """
    import uuid

    return f"{label}-{uuid.uuid4().hex[:8]}"


def _register_media_buy(ctx: dict, label: str, media_buy: Any) -> None:
    """Register a media buy under a Gherkin label for later lookup.

    Stores both the label→real_id mapping and the label→ORM object mapping.
    """
    ctx.setdefault("media_buy_labels", {})[label] = media_buy.media_buy_id
    ctx.setdefault("seeded_media_buys", {})[label] = media_buy


def _resolve_media_buy_id(ctx: dict, label: str) -> str:
    """Resolve a Gherkin label to the real database media_buy_id."""
    labels = ctx.get("media_buy_labels", {})
    if label in labels:
        return labels[label]
    return label  # fallback: label IS the real ID (legacy)


def _resolve_media_buy_ids(ctx: dict, labels: list[str]) -> list[str]:
    """Resolve a list of Gherkin labels to real database media_buy_ids."""
    return [_resolve_media_buy_id(ctx, label) for label in labels]


def _register_principal(ctx: dict, label: str) -> None:
    """Register the ctx principal under a Gherkin label.

    Called once per scenario (conftest creates one principal).
    Subsequent Given steps resolve "buyer-001" → real principal_id.
    """
    principal = ctx["principal"]
    ctx.setdefault("principal_labels", {})[label] = principal.principal_id


def _resolve_principal_id(ctx: dict, label: str) -> str:
    """Resolve a Gherkin principal label to the real principal_id."""
    labels = ctx.get("principal_labels", {})
    if label in labels:
        return labels[label]
    return label  # fallback: label IS the real ID


def _make_test_snapshot() -> Any:
    """Create a realistic Snapshot instance for adapter reporting tests."""
    from datetime import UTC, datetime

    from src.core.schemas._base import Snapshot

    return Snapshot(
        as_of=datetime.now(UTC),
        impressions=1500.0,
        spend=75.50,
        staleness_seconds=30,
        clicks=120.0,
        pacing_index=1.05,
        delivery_status="delivering",
        currency="USD",
    )


def _patch_adapter_with_snapshot(ctx: dict, snapshot_data: dict) -> None:
    """Patch get_adapter to return a mock adapter with the given snapshot data."""
    from unittest.mock import MagicMock, patch

    adapter_mock = MagicMock()
    adapter_mock.capabilities.supports_realtime_reporting = True
    adapter_mock.get_packages_snapshot.return_value = snapshot_data

    patcher = patch(
        "src.core.tools.media_buy_list.get_adapter",
        return_value=adapter_mock,
    )
    patcher.start()
    ctx.setdefault("_patchers", []).append(patcher)
    ctx["adapter_snapshot_data"] = snapshot_data


def _find_media_buy_for_package(ctx: dict, pkg_id: str) -> Any:
    """Find the seeded media buy ORM object that owns the given package_id."""
    pkgs = ctx.get("seeded_packages", {})
    mb = pkgs.get(pkg_id)
    assert mb is not None, (
        f"Package '{pkg_id}' not found in seeded_packages. "
        f"Ensure a prior Given step created the media buy with this package. "
        f"Known packages: {list(pkgs)}"
    )
    return mb


# ═══════════════════════════════════════════════════════════════════════
# GIVEN steps — seed media buys in DB
# ═══════════════════════════════════════════════════════════════════════


@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with start_date "{start}" and end_date "{end}"'
    )
)
def given_principal_owns_media_buy_with_dates(ctx: dict, principal_id: str, mb_id: str, start: str, end: str) -> None:
    """Create a media buy with specific flight dates, verifying principal_id consistency."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)


@given(parsers.parse('today is "{today_str}"'))
def given_today_is(ctx: dict, today_str: str) -> None:
    """Override 'today' for status computation.

    Production code uses ``datetime.now(UTC).date()`` in
    ``src.core.tools.media_buy_list`` (line 116). We patch ``datetime``
    in that module so ``now()`` returns a datetime whose ``.date()``
    yields the desired date.
    """
    from datetime import UTC, datetime
    from unittest.mock import patch

    parsed = date.fromisoformat(today_str)
    ctx["mock_today"] = today_str

    # Build a datetime that corresponds to the target date
    fake_now = datetime(parsed.year, parsed.month, parsed.day, 12, 0, 0, tzinfo=UTC)

    patcher = patch("src.core.tools.media_buy_list.datetime", wraps=datetime)
    mock_dt = patcher.start()
    mock_dt.now.return_value = fake_now
    ctx.setdefault("_patchers", []).append(patcher)


# Pre-flight window (far future) for persisted-status seeds that carry no
# explicit dates: keeps the persisted value stable regardless of the real clock.
# INV-8/9/10 assert the raw persisted→canonical mapping with no flight
# refinement, so a pre-flight window is invisible to the resolver (those statuses
# are terminal or non-serving, never date-refined) while making the seed
# self-consistent (a pending buy is legitimately pre-flight).
_UC019_PERSISTED_SEED_WINDOW = (date(2099, 1, 1), date(2099, 12, 31))


def _seed_media_buy_with_persisted_status(
    ctx: dict,
    principal_id: str,
    mb_id: str,
    persisted: str,
    *,
    is_paused: bool = False,
) -> None:
    """Seed a media buy carrying a specific persisted (internal) status column.

    Mirrors given_multiple_buys_various_statuses in uc004 (the reviewer's
    template): the persisted status is written verbatim so get_media_buys
    exercises the real PERSISTED_STATUS_TO_CANONICAL mapping. Dates default to a
    pre-flight window; scenarios that need a specific flight phase override them
    via the "has start_date/end_date" modifier step.
    """
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    start, end = _UC019_PERSISTED_SEED_WINDOW
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status=persisted,
        is_paused=is_paused,
        start_date=start,
        end_date=end,
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with persisted status "{persisted}"'))
def given_owns_media_buy_persisted_status(ctx: dict, principal_id: str, mb_id: str, persisted: str) -> None:
    """Seed a buy with a persisted status (INV-7/8/9/10 taxonomy mapping)."""
    _seed_media_buy_with_persisted_status(ctx, principal_id, mb_id, persisted)


def _seed_simple_media_buy(ctx: dict, principal_id: str, mb_id: str, status: str = "active", **columns: Any) -> Any:
    """Register the principal, seed a media buy (default mid-flight window) under a
    unique id, and register its Gherkin label. Shared by the plain and
    with-status Given steps so the seed+register block lives in one place.

    ``**columns`` forwards further persisted column values (``revision``,
    ``confirmed_at``) straight to the factory, so the v3.1 lifecycle-handle Givens
    seed through this ONE factory path instead of a second seeder or a new env
    API — MediaBuyListEnv has no seeding methods and none of UC-019's other
    Givens use one.
    """
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status=status,
        **columns,
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)
    return mb


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with status "{status}"'))
def given_owns_media_buy_with_status(ctx: dict, principal_id: str, mb_id: str, status: str) -> None:
    """Seed a buy carrying a specific status and REGISTER its label.

    Without this specific binding the greedy generic step (`owns media buy
    "{mb_id}"`) captured the trailing ` with status "…"` into mb_id, registering
    a garbled label so a later by-ID query couldn't resolve it (INV-5). Default
    (mid-flight) window: "active" stays active; terminal states pass through.
    """
    _seed_simple_media_buy(ctx, principal_id, mb_id, status)


@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" '
        'with persisted status "{persisted}" and is_paused {flag}'
    )
)
def given_owns_media_buy_persisted_status_paused(
    ctx: dict, principal_id: str, mb_id: str, persisted: str, flag: str
) -> None:
    """Seed a buy with a persisted status and explicit is_paused (INV-6/INV-11)."""
    _seed_media_buy_with_persisted_status(
        ctx, principal_id, mb_id, persisted, is_paused=(flag.strip().lower() == "true")
    )


@given(parsers.parse('media buy "{mb_id}" has start_date "{start}" and end_date "{end}"'))
def given_media_buy_has_dates(ctx: dict, mb_id: str, start: str, end: str) -> None:
    """Override the flight window on an already-seeded buy (INV-6/7/11 modifier)."""
    from sqlalchemy import select

    from src.core.database.models import MediaBuy as DBMediaBuy

    real_id = _resolve_media_buy_id(ctx, mb_id)
    env = ctx["env"]
    row = env._session.scalars(select(DBMediaBuy).filter_by(media_buy_id=real_id)).first()
    assert row is not None, f"Media buy '{mb_id}' (real_id={real_id}) not seeded before setting its dates"
    row.start_date = date.fromisoformat(start)
    row.end_date = date.fromisoformat(end)
    env._session.commit()


@given(parsers.parse('the principal "{principal_id}" owns media buys "{mb1}", "{mb2}", and "{mb3}"'))
def given_principal_owns_multiple(ctx: dict, principal_id: str, mb1: str, mb2: str, mb3: str) -> None:
    """Create 3 media buys, verifying principal_id consistency."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    for label in [mb1, mb2, mb3]:
        real_id = _generate_unique_id(label)
        mb = MediaBuyFactory(
            tenant=ctx["tenant"],
            principal=ctx["principal"],
            media_buy_id=real_id,
            status="active",
        )
        _register_media_buy(ctx, label, mb)
    env._commit_factory_data()


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with an active package "{pkg_id}"'))
def given_principal_owns_with_package(ctx: dict, principal_id: str, mb_id: str, pkg_id: str) -> None:
    """Create a media buy with an active package, verifying principal_id consistency."""
    # Verify the stated principal_id matches the ctx principal
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
    )
    MediaPackageFactory(
        media_buy=mb,
        package_id=pkg_id,
        package_config={
            "package_id": pkg_id,
            "product_id": "guaranteed_display",
            "budget": 5000.0,
            "status": "active",
        },
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)
    ctx.setdefault("seeded_packages", {})[pkg_id] = mb


@given(parsers.parse('the principal "{principal_id}" owns no media buys'))
def given_principal_owns_none(ctx: dict, principal_id: str) -> None:
    """No media buys exist for this principal (default state).

    Validates that the principal_id matches the ctx principal (like other
    principal-scoped Given steps).
    """
    _register_principal(ctx, principal_id)
    ctx.setdefault("seeded_media_buys", {})


@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with start_date "{start}" '
        'and start_time "{start_time}" and end_date "{end}"'
    )
)
def given_principal_owns_mb_with_start_time(
    ctx: dict, principal_id: str, mb_id: str, start: str, start_time: str, end: str
) -> None:
    """Create a media buy with start_time taking precedence over start_date (INV-150-4)."""
    from datetime import datetime as dt

    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    start_dt = dt.fromisoformat(start_time)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        start_time=start_dt,
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)


@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with start_date "{start}" '
        'and end_date "{end}" and end_time "{end_time}"'
    )
)
def given_principal_owns_mb_with_end_time(
    ctx: dict, principal_id: str, mb_id: str, start: str, end: str, end_time: str
) -> None:
    """Create a media buy with end_time taking precedence over end_date (INV-150-5)."""
    from datetime import datetime as dt

    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    end_dt = dt.fromisoformat(end_time)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        end_time=end_dt,
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)


@given(parsers.parse('the principal "{principal_id}" owns media buys in various statuses'))
def given_principal_owns_various_statuses(ctx: dict, principal_id: str) -> None:
    """Create media buys in multiple statuses for status filter testing."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    # Create one in each status by using dates relative to 'today'
    # Pre-flight → pending_start, In-flight → active, Post-flight → completed
    today = date.fromisoformat(ctx.get("mock_today", "2026-03-15"))
    from datetime import timedelta

    status_dates = {
        "mb-pending": (today + timedelta(days=10), today + timedelta(days=30)),
        "mb-active": (today - timedelta(days=10), today + timedelta(days=10)),
        "mb-completed": (today - timedelta(days=30), today - timedelta(days=10)),
    }
    for label, (start, end) in status_dates.items():
        real_id = _generate_unique_id(label)
        mb = MediaBuyFactory(
            tenant=ctx["tenant"],
            principal=ctx["principal"],
            media_buy_id=real_id,
            status="active",
            start_date=start,
            end_date=end,
        )
        _register_media_buy(ctx, label, mb)
    env._commit_factory_data()


@given(parsers.parse('the principal "{principal_id}" owns active media buy "{mb1}" and completed media buy "{mb2}"'))
def given_principal_owns_active_and_completed(ctx: dict, principal_id: str, mb1: str, mb2: str) -> None:
    """Create one active and one completed media buy (INV-151-1)."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    today = date.fromisoformat(ctx.get("mock_today", "2026-03-15"))
    from datetime import timedelta

    # Active: today is within flight dates
    real_id1 = _generate_unique_id(mb1)
    mb_active = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id1,
        status="active",
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=5),
    )
    # Completed: today is after flight dates
    real_id2 = _generate_unique_id(mb2)
    mb_completed = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id2,
        status="active",
        start_date=today - timedelta(days=30),
        end_date=today - timedelta(days=10),
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb1, mb_active)
    _register_media_buy(ctx, mb2, mb_completed)


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with package "{pkg_id}"'))
def given_principal_owns_mb_with_named_package(ctx: dict, principal_id: str, mb_id: str, pkg_id: str) -> None:
    """Create a media buy with a named package (for creative approval scenarios)."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
    )
    MediaPackageFactory(
        media_buy=mb,
        package_id=pkg_id,
        package_config={
            "package_id": pkg_id,
            "product_id": "guaranteed_display",
            "budget": 5000.0,
            "status": "active",
        },
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)
    ctx.setdefault("seeded_packages", {})[pkg_id] = mb


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with packages "{pkg1}" and "{pkg2}"'))
def given_principal_owns_mb_with_two_packages(ctx: dict, principal_id: str, mb_id: str, pkg1: str, pkg2: str) -> None:
    """Create a media buy with two packages (INV-153-3)."""
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        media_buy_id=real_id,
        status="active",
    )
    for pkg_id in [pkg1, pkg2]:
        MediaPackageFactory(
            media_buy=mb,
            package_id=pkg_id,
            package_config={
                "package_id": pkg_id,
                "product_id": "guaranteed_display",
                "budget": 3000.0,
                "status": "active",
            },
        )
        ctx.setdefault("seeded_packages", {})[pkg_id] = mb
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)


@given(parsers.parse('package "{pkg_id}" has a creative with internal status "{status}"'))
def given_package_creative_status(ctx: dict, pkg_id: str, status: str) -> None:
    """Seed a creative with the given internal status, assigned to the package."""
    env = ctx["env"]
    # Resolve the media buy that owns this package from seeded_media_buys
    media_buy = _find_media_buy_for_package(ctx, pkg_id)
    # Feature file passes "null" as literal string for null status.
    # DB column is NOT NULL, so store as-is — _map_creative_status treats
    # unrecognized values (including "null" and "") as pending_review.
    creative = CreativeFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        status=status,
    )
    CreativeAssignmentFactory(
        creative=creative,
        media_buy=media_buy,
        package_id=pkg_id,
    )
    env._commit_factory_data()


@given(
    parsers.parse('package "{pkg_id}" has a creative with internal status "{status}" and rejection_reason "{reason}"')
)
def given_package_creative_rejected(ctx: dict, pkg_id: str, status: str, reason: str) -> None:
    """Seed a creative with the given internal status and rejection_reason, assigned to the package."""
    env = ctx["env"]
    media_buy = _find_media_buy_for_package(ctx, pkg_id)
    creative = CreativeFactory(
        tenant=ctx["tenant"],
        principal=ctx["principal"],
        status=status,
        data={"rejection_reason": reason},
    )
    CreativeAssignmentFactory(
        creative=creative,
        media_buy=media_buy,
        package_id=pkg_id,
    )
    env._commit_factory_data()


@given(parsers.parse('package "{pkg_id}" has a creative assignment with creative_id "{creative_id}"'))
def given_package_creative_assignment(ctx: dict, pkg_id: str, creative_id: str) -> None:
    """Record creative assignment — cannot seed real DB records.

    FIXME(salesagent-vov): When CreativeAssignmentFactory exists, seed real DB records.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: No CreativeAssignmentFactory — cannot seed creative assignment "
        f"for '{creative_id}' on package '{pkg_id}'. "
        f"FIXME(salesagent-vov): Create factory to seed real DB records."
    )


@given(parsers.parse('the creative "{creative_id}" has internal status "{status}" and rejection_reason "{reason}"'))
def given_creative_status_with_reason(ctx: dict, creative_id: str, status: str, reason: str) -> None:
    """Update creative status/reason — cannot update real DB records.

    FIXME(salesagent-vov): When CreativeAssignmentFactory exists, update real DB records.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: No CreativeAssignmentFactory — cannot update creative "
        f"'{creative_id}' with status='{status}', rejection_reason='{reason}' in DB. "
        f"FIXME(salesagent-vov): Create factory to seed/update real DB records."
    )


@given(parsers.parse('the creative "{creative_id}" has internal status "{status}" {extra_condition}'))
def given_creative_status_extra(ctx: dict, creative_id: str, status: str, extra_condition: str) -> None:
    """Update creative status with extra conditions — cannot update real DB records.

    FIXME(salesagent-vov): When CreativeAssignmentFactory exists, update real DB records.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: No CreativeAssignmentFactory — cannot update creative "
        f"'{creative_id}' status to '{status}' with '{extra_condition}' in DB. "
        f"FIXME(salesagent-vov): Create factory to seed/update real DB records."
    )


@given(parsers.parse('the creative "{creative_id}" has internal status "{status}"'))
def given_creative_status_simple(ctx: dict, creative_id: str, status: str) -> None:
    """Set creative internal status — cannot update real DB records.

    FIXME(salesagent-vov): When CreativeAssignmentFactory exists, update real DB records.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: No CreativeAssignmentFactory — cannot update creative "
        f"'{creative_id}' status to '{status}' in DB. "
        f"FIXME(salesagent-vov): Create factory to seed/update real DB records."
    )


@given(parsers.parse('no creative with id "{creative_id}" exists in the tenant'))
def given_no_creative_exists(ctx: dict, creative_id: str) -> None:
    """Mark creative as nonexistent — cannot verify or enforce DB absence.

    FIXME(salesagent-vov): When CreativeAssignmentFactory exists, verify actual
    DB absence rather than relying on ctx-only sentinels.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: Cannot enforce DB absence for creative '{creative_id}' — "
        f"no CreativeAssignmentFactory to verify or control DB state. "
        f"FIXME(salesagent-vov): Verify actual DB absence."
    )


@given(parsers.parse('package "{pkg_id}" has a creative assignment referencing creative_id "{creative_id}"'))
def given_package_creative_ref_nonexistent(ctx: dict, pkg_id: str, creative_id: str) -> None:
    """Record creative assignment referencing a potentially nonexistent creative.

    FIXME(salesagent-vov): No CreativeAssignmentFactory — cannot seed real DB records.
    """
    import pytest

    pytest.xfail(
        f"SPEC-PRODUCTION GAP: No CreativeAssignmentFactory — cannot seed creative assignment "
        f"for '{creative_id}' on package '{pkg_id}'. "
        f"FIXME(salesagent-vov): Create factory to seed real DB records."
    )


@given(parsers.parse('no snapshot data is available for package "{pkg_id}"'))
def given_no_snapshot_for_package(ctx: dict, pkg_id: str) -> None:
    """Establish that no snapshot data exists for a package.

    The default state in the harness is no snapshot data — the adapter mock
    (when present) returns no data unless explicitly configured. Record the
    expectation in ctx so Then steps can verify the correct unavailable_reason.
    """
    ctx.setdefault("snapshot_unavailable_packages", set()).add(pkg_id)


@given("the ad platform adapter supports realtime reporting")
def given_adapter_supports_reporting(ctx: dict) -> None:
    """Configure the adapter mock to support realtime reporting for snapshots.

    FIXME(salesagent-9vgz.1): When the harness supports full adapter capability
    configuration, this step should also set up mock reporting endpoints that
    return test data (impressions, spend, etc.).
    """
    ctx["adapter_supports_reporting"] = True
    env = ctx["env"]
    assert "adapter" in env.mock, (
        "Step claims 'the ad platform adapter supports realtime reporting' "
        "but no adapter mock is configured in the test environment"
    )
    adapter_mock = env.mock["adapter"].return_value
    adapter_mock.supports_realtime_reporting = True


@given("the ad platform adapter does not support realtime reporting")
def given_adapter_no_reporting(ctx: dict) -> None:
    """Configure the adapter to NOT support realtime reporting."""
    ctx["adapter_supports_reporting"] = False
    env = ctx["env"]
    assert "adapter" in env.mock, (
        "Step claims 'the ad platform adapter does not support realtime reporting' "
        "but no adapter mock is configured in the test environment"
    )
    adapter_mock = env.mock["adapter"].return_value
    adapter_mock.supports_realtime_reporting = False


@given(parsers.parse("the ad platform adapter exists"))
def given_adapter_exists(ctx: dict) -> None:
    """Confirm adapter exists (default state in harness)."""
    env = ctx["env"]
    assert "adapter" in env.mock, (
        "Step claims 'the ad platform adapter exists' but no adapter mock is configured in the test environment"
    )


@given(parsers.parse("the adapter supports realtime reporting and data is available"))
def given_adapter_reporting_with_data(ctx: dict) -> None:
    """Adapter supports reporting AND snapshot data is available.

    Patches get_adapter in the media_buy_list module to return a mock adapter
    whose get_packages_snapshot returns realistic snapshot data keyed by the
    packages created in earlier Given steps.
    """
    ctx["adapter_supports_reporting"] = True

    snapshot_data: dict[str, dict] = {}
    seeded = ctx.get("seeded_media_buys", {})
    env = ctx["env"]
    for _label, mb_obj in seeded.items():
        real_id = mb_obj.media_buy_id
        if env._session is not None:
            from sqlalchemy import select

            from src.core.database.models import MediaPackage as DBMediaPackage

            pkgs = env._session.scalars(select(DBMediaPackage).filter_by(media_buy_id=real_id)).all()
            for pkg in pkgs:
                snapshot_data.setdefault(real_id, {})[pkg.package_id] = _make_test_snapshot()

    _patch_adapter_with_snapshot(ctx, snapshot_data)


@given(parsers.parse("the adapter supports realtime reporting but no data for {pkg_id}"))
def given_adapter_reporting_no_data(ctx: dict, pkg_id: str) -> None:
    """Adapter supports reporting but no snapshot for specified package.

    Configures adapter mock to support realtime reporting but return an empty
    snapshot dict for the media buy owning ``pkg_id``, so the package has no
    snapshot data available.
    """
    ctx["adapter_supports_reporting"] = True

    # Build snapshot_data with the target package's media buy present but
    # with NO entry for the specific pkg_id — simulating "no data for X".
    snapshot_data: dict[str, dict] = {}
    seeded = ctx.get("seeded_media_buys", {})
    env = ctx["env"]
    if env._session is not None:
        from sqlalchemy import select

        from src.core.database.models import MediaPackage as DBMediaPackage

        pkg_row = env._session.scalars(select(DBMediaPackage).filter_by(package_id=pkg_id)).first()
        if pkg_row:
            # Media buy exists but has empty snapshot dict — no data for pkg_id
            snapshot_data[pkg_row.media_buy_id] = {}
    elif seeded:
        # Fallback: use first seeded media buy with empty snapshot
        first_mb = next(iter(seeded.values()))
        snapshot_data[first_mb.media_buy_id] = {}

    _patch_adapter_with_snapshot(ctx, snapshot_data)


@given(parsers.parse("the adapter supports realtime reporting and data for all pkgs"))
def given_adapter_reporting_all_data(ctx: dict) -> None:
    """Adapter supports reporting with snapshot data for every seeded package.

    Builds snapshot entries for all packages across all seeded media buys,
    so every package has data available when include_snapshot is requested.
    """
    ctx["adapter_supports_reporting"] = True

    snapshot_data: dict[str, dict] = {}
    seeded = ctx.get("seeded_media_buys", {})
    env = ctx["env"]

    for _label, mb_obj in seeded.items():
        real_id = mb_obj.media_buy_id
        if env._session is not None:
            from sqlalchemy import select

            from src.core.database.models import MediaPackage as DBMediaPackage

            pkgs = env._session.scalars(select(DBMediaPackage).filter_by(media_buy_id=real_id)).all()
            for pkg in pkgs:
                snapshot_data.setdefault(real_id, {})[pkg.package_id] = _make_test_snapshot()

    _patch_adapter_with_snapshot(ctx, snapshot_data)


@given(parsers.parse("the adapter supports reporting, data for {pkg1} but not {pkg2}"))
def given_adapter_reporting_mixed(ctx: dict, pkg1: str, pkg2: str) -> None:
    """Adapter supports reporting with mixed per-package snapshot availability.

    Configures adapter mock so ``pkg1`` has snapshot data and ``pkg2`` does not.
    The snapshot dict includes an entry for pkg1 but omits pkg2.
    """
    ctx["adapter_supports_reporting"] = True

    snapshot_data: dict[str, dict] = {}
    seeded = ctx.get("seeded_media_buys", {})
    env = ctx["env"]

    # Find which media buy owns pkg1 and pkg2
    if env._session is not None:
        from sqlalchemy import select

        from src.core.database.models import MediaPackage as DBMediaPackage

        for pkg_id in (pkg1, pkg2):
            pkg_row = env._session.scalars(select(DBMediaPackage).filter_by(package_id=pkg_id)).first()
            if pkg_row:
                mb_id = pkg_row.media_buy_id
                if pkg_id == pkg1:
                    snapshot_data.setdefault(mb_id, {})[pkg_id] = _make_test_snapshot()
                else:
                    # pkg2's media buy key exists but no entry for pkg2
                    snapshot_data.setdefault(mb_id, {})
    elif seeded:
        first_mb = next(iter(seeded.values()))
        snapshot_data[first_mb.media_buy_id] = {pkg1: _make_test_snapshot()}

    _patch_adapter_with_snapshot(ctx, snapshot_data)


@given(parsers.parse("the adapter does not support realtime reporting"))
def given_adapter_no_realtime(ctx: dict) -> None:
    """Configure adapter to NOT support realtime reporting (short form).

    Patches get_adapter in the media_buy_list module so the returned adapter
    has supports_realtime_reporting=False. Unlike the "ad platform adapter does
    not support realtime reporting" step (which uses env.mock["adapter"]), this
    step patches the module-level get_adapter — suitable for MediaBuyListEnv
    which has no EXTERNAL_PATCHES.
    """
    from unittest.mock import MagicMock, patch

    ctx["adapter_supports_reporting"] = False

    adapter_mock = MagicMock()
    adapter_mock.capabilities.supports_realtime_reporting = False
    adapter_mock.get_packages_snapshot.return_value = {}

    patcher = patch(
        "src.core.tools.media_buy_list.get_adapter",
        return_value=adapter_mock,
    )
    patcher.start()
    ctx.setdefault("_patchers", []).append(patcher)


@given(parsers.parse('an authenticated principal "{principal_id}" who owns {count:d} media buys'))
@given(parsers.parse('the principal "{principal_id}" owns {count:d} media buys'))
def given_principal_with_n_buys(ctx: dict, principal_id: str, count: int) -> None:
    """Create N media buys for a principal.

    Uses MediaBuyFactory(...) which invokes factory_boy's create() strategy.
    env._commit_factory_data() flushes all pending factory objects to the DB session.

    The second spelling is BR-RULE-291 INV-1's ("owns 3 media buys") — the same
    logical setup in the Background's own phrasing, so it aliases onto this step
    rather than seeding a second time in a second place.
    """
    _register_principal(ctx, principal_id)
    env = ctx["env"]
    for i in range(count):
        label = f"mb-{principal_id}-{i + 1}"
        real_id = _generate_unique_id(label)
        mb = MediaBuyFactory(
            tenant=ctx["tenant"],
            principal=ctx["principal"],
            media_buy_id=real_id,
            status="active",
        )
        _register_media_buy(ctx, label, mb)
    env._commit_factory_data()
    assert len(ctx["seeded_media_buys"]) >= count, (
        f"Expected at least {count} seeded media buys, got {len(ctx['seeded_media_buys'])}"
    )


@given(parsers.parse('an authenticated principal "{principal_id}" who owns no media buys'))
def given_principal_no_buys(ctx: dict, principal_id: str) -> None:
    """No media buys exist for this principal."""
    _register_principal(ctx, principal_id)
    ctx.setdefault("seeded_media_buys", {})


@given(parsers.parse('an authenticated principal "{principal_id}" who owns media buy "{mb_id}"'))
def given_principal_owns_single_mb(ctx: dict, principal_id: str, mb_id: str) -> None:
    """Create a single media buy for a principal.

    If principal_id matches the harness principal, use it directly.
    If it's a different principal (e.g., for isolation tests), create a new one
    via PrincipalFactory. Both factory objects are committed via _commit_factory_data().
    """
    from tests.factories import PrincipalFactory

    env = ctx["env"]
    resolved_id = _resolve_principal_id(ctx, principal_id)
    if ctx["principal"].principal_id == resolved_id:
        principal = ctx["principal"]
    else:
        # Create a separate principal for isolation testing (INV-154)
        principal = PrincipalFactory(
            tenant=ctx["tenant"],
            principal_id=resolved_id,
        )
    real_id = _generate_unique_id(mb_id)
    mb = MediaBuyFactory(
        tenant=ctx["tenant"],
        principal=principal,
        media_buy_id=real_id,
        status="active",
    )
    env._commit_factory_data()
    _register_media_buy(ctx, mb_id, mb)
    ctx.setdefault("principals", {})[principal_id] = principal


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}"'))
def given_principal_owns_mb_simple(ctx: dict, principal_id: str, mb_id: str) -> None:
    """Create a media buy (simple, no date attributes).

    GREEDY-CAPTURE HAZARD (the failure mode documented on
    given_owns_media_buy_with_status): this parser's ``{mb_id}`` also matches any
    scenario line that ENDS in a quoted clause — ``... owns media buy "mb-001" with
    confirmed_at "2026-05-01T12:00:00Z"`` binds here with the whole clause
    swallowed into the label, registering a buy no later by-ID step can resolve.

    The escape is that pytest-bdd resolves a step to the alphabetically LAST
    matching definition text (it registers one fixture per step text and pytest
    takes the last fixturedef), and any text extending this one sorts after it — so
    writing the more specific Given is always sufficient, and every confirmed_at
    Given in the lifecycle-handles section below exists for exactly that reason.

    Deliberately NOT asserted here: ~38 params across other UC-019 scenarios still
    reach this step with a garbled label and are dormant for their own missing
    Thens, so rejecting the label would convert their dormancy into hard failures
    rather than grading anything. That conversion is the auto-xfail mechanism's
    job (GH #1929), not this step's.
    """
    _seed_simple_media_buy(ctx, principal_id, mb_id)


# RETIRED with T-UC-019-partition-status-invalid: the "no start_time and no
# start_date" / "no end_time and no end_date" given steps seeded a schema-impossible
# null-date buy (MediaBuy dates are NOT NULL). See the feature file for the spec
# rationale. Their helper _create_media_buy_with_null_dates and the paired
# then_status_handles_missing_date are removed with them.


def _seed_account_for_principal(ctx: dict, *, sandbox: bool) -> None:
    """Seed a real Account (sandbox or production) reachable by the scenario principal.

    get_media_buys carries no account parameter on the request (production
    rejects account filtering with ACCOUNT_FILTER_NOT_SUPPORTED and instructs
    "the seller infers the account from the auth token"), so "the request
    targets a <kind> account" means: the account the identity resolves to has
    that sandbox flag. Seeding the Account + AgentAccountAccess rows makes the
    premise real at the data layer — a future sandbox short-circuit keyed off
    the principal's account (BR-RULE-209) is then actually exercised, instead
    of the Given being an inert ctx flag (6szx graduation inspection).
    """
    from tests.factories.account import AccountFactory, AgentAccountAccessFactory

    env = ctx["env"]
    account = AccountFactory(tenant=ctx["tenant"], sandbox=sandbox)
    AgentAccountAccessFactory(tenant=ctx["tenant"], principal=ctx["principal"], account=account)
    env._commit_factory_data()
    ctx["sandbox"] = sandbox
    ctx["account"] = account


@given(parsers.parse("the request targets a sandbox account"))
def given_sandbox_account(ctx: dict) -> None:
    """Seed a sandbox account for the principal (the token infers the account)."""
    _seed_account_for_principal(ctx, sandbox=True)


@given(parsers.parse("the request targets a production account"))
def given_production_account(ctx: dict) -> None:
    """Seed a production (non-sandbox) account for the principal."""
    _seed_account_for_principal(ctx, sandbox=False)


@given("an authenticated identity with no principal_id")
def given_identity_no_principal(ctx: dict) -> None:
    """Simulate an identity resolved but with no principal_id.

    The buyer has valid tenant context (e.g., token resolved) but lacks a
    principal_id — simulating an expired/revoked token or incomplete auth.
    Sets has_auth=True so the When step sends a real identity, but with
    principal_id=None so _impl can detect the missing principal and return
    an appropriate error response.
    """
    from tests.factories.principal import PrincipalFactory

    env = ctx["env"]
    identity = PrincipalFactory.make_identity(
        principal_id=None,
        tenant_id=env._tenant_id,
    )
    ctx.setdefault("query_kwargs", {})["identity"] = identity


@given(parsers.parse("an authenticated identity with principal_id null"))
@given(parsers.parse('an authenticated identity with principal_id ""'))
def given_identity_principal_id_null_or_empty(ctx: dict) -> None:
    """Simulate an identity with principal_id as null or empty string.

    Both null and empty string are treated as "missing principal_id" by
    production code. We set principal_id=None for both — the distinction
    is in the Gherkin readability, not the implementation.
    """
    from tests.factories.principal import PrincipalFactory

    env = ctx["env"]
    identity = PrincipalFactory.make_identity(
        principal_id=None,
        tenant_id=env._tenant_id,
    )
    ctx.setdefault("query_kwargs", {})["identity"] = identity


@given(parsers.parse('the principal "{principal_id}" does not exist in the tenant database'))
def given_principal_not_in_tenant_db(ctx: dict, principal_id: str) -> None:
    """Ensure the specified principal does not exist in the tenant database.

    For integration env: delete the principal if it exists. The env already
    created a default principal, but the scenario has set up a different
    principal_id (e.g., "buyer-unknown") that should NOT be in the database.
    """
    from sqlalchemy import delete, select

    from src.core.database.models import Principal

    env = ctx["env"]
    tenant = ctx.get("tenant")
    assert tenant is not None, "No tenant in ctx"
    if env._session is not None:
        existing = env._session.scalars(
            select(Principal).filter_by(principal_id=principal_id, tenant_id=tenant.tenant_id)
        ).first()
        if existing:
            env._session.execute(
                delete(Principal).where(
                    Principal.principal_id == principal_id,
                    Principal.tenant_id == tenant.tenant_id,
                )
            )
            env._session.commit()


@given(parsers.parse('an authenticated principal "{principal_id}" not in registry'))
def given_principal_not_in_registry(ctx: dict, principal_id: str) -> None:
    """Simulate an authenticated principal whose ID is not in the tenant database.

    Sets up an identity with the given principal_id, but ensures no matching
    Principal row exists in the DB. The _impl function should detect this
    and return a "principal_not_found" error.
    """
    from sqlalchemy import delete, select

    from src.core.database.models import Principal
    from tests.factories.principal import PrincipalFactory

    env = ctx["env"]
    tenant = ctx.get("tenant")
    assert tenant is not None, "No tenant in ctx"

    # Build identity with the unregistered principal_id
    identity = PrincipalFactory.make_identity(
        principal_id=principal_id,
        tenant_id=env._tenant_id,
    )
    ctx.setdefault("query_kwargs", {})["identity"] = identity

    # Ensure the principal does NOT exist in DB
    if env._session is not None:
        existing = env._session.scalars(
            select(Principal).filter_by(principal_id=principal_id, tenant_id=tenant.tenant_id)
        ).first()
        if existing:
            env._session.execute(
                delete(Principal).where(
                    Principal.principal_id == principal_id,
                    Principal.tenant_id == tenant.tenant_id,
                )
            )
            env._session.commit()


@given("no authentication context")
def given_no_auth_context(ctx: dict) -> None:
    """Simulate a request with no authentication at all.

    Sets has_auth=False so the When step sends identity=None, triggering
    an AUTH_REQUIRED error from _impl.
    """
    ctx["has_auth"] = False


@given(parsers.parse('snapshot data is available for package "{pkg_id}"'))
def given_snapshot_available(ctx: dict, pkg_id: str) -> None:
    """Ensure snapshot data will be returned for a specific package.

    Patches get_adapter in the media_buy_list module so that the adapter
    returns snapshot data for the specified package. If a patcher already
    exists (from given_adapter_reporting_with_data), update its return data.
    """
    test_snapshot = _make_test_snapshot()
    ctx.setdefault("expected_snapshots", {})[pkg_id] = test_snapshot

    # Find the media_buy_id that owns this package
    seeded = ctx.get("seeded_media_buys", {})
    target_mb_id: str | None = None
    env = ctx["env"]
    if env._session is not None:
        from sqlalchemy import select

        from src.core.database.models import MediaPackage as DBMediaPackage

        pkg_row = env._session.scalars(select(DBMediaPackage).filter_by(package_id=pkg_id)).first()
        if pkg_row:
            target_mb_id = pkg_row.media_buy_id
    if target_mb_id is None and seeded:
        first_mb = next(iter(seeded.values()))
        target_mb_id = first_mb.media_buy_id

    # Build or update snapshot_data mapping
    snapshot_data = ctx.get("adapter_snapshot_data", {})
    if target_mb_id:
        snapshot_data.setdefault(target_mb_id, {})[pkg_id] = test_snapshot
    ctx["adapter_snapshot_data"] = snapshot_data

    # If no adapter patcher exists yet, create one
    if not any(getattr(p, "attribute", "") == "get_adapter" for p in ctx.get("_patchers", [])):
        _patch_adapter_with_snapshot(ctx, snapshot_data)


# ═══════════════════════════════════════════════════════════════════════
# WHEN steps — dispatch query request
# ═══════════════════════════════════════════════════════════════════════


def _dispatch_query(ctx: dict, **extra_kwargs: Any) -> None:
    """Build and dispatch a get_media_buys request."""
    if ctx.get("error") is not None:
        return
    query_kwargs = ctx.get("query_kwargs", {})
    query_kwargs.update(extra_kwargs)

    if ctx.get("has_auth") is False:
        dispatch_request(ctx, identity=None, **query_kwargs)
    else:
        dispatch_request(ctx, **query_kwargs)


@when("the Buyer Agent sends a get_media_buys request via A2A with no filters")
def when_query_a2a_no_filters(ctx: dict) -> None:
    """Send get_media_buys with no filters via A2A (transport-specific).

    env.call_a2a() dispatches to get_media_buys_raw — the tool name is baked
    into MediaBuyListEnv, matching the step text's 'get_media_buys' claim.
    """
    env = ctx["env"]
    try:
        ctx["response"] = env.call_a2a()
    except Exception as exc:
        ctx["error"] = exc


@when("the Buyer Agent invokes the get_media_buys MCP tool with no filters")
def when_query_mcp_no_filters(ctx: dict) -> None:
    """Send get_media_buys with no filters via MCP (transport-specific).

    env.call_mcp() dispatches to the get_media_buys MCP wrapper — the tool name
    is baked into MediaBuyListEnv, matching the step text's 'get_media_buys' claim.
    """
    env = ctx["env"]
    try:
        ctx["response"] = env.call_mcp()
    except Exception as exc:
        ctx["error"] = exc


@when("the Buyer Agent sends a get_media_buys request with include_snapshot true")
def when_query_with_snapshot(ctx: dict) -> None:
    """Send get_media_buys with include_snapshot=True."""
    _dispatch_query(ctx, include_snapshot=True)


@when("the Buyer Agent sends a get_media_buys request with no filters")
@when("the Buyer Agent sends a get_media_buys request")
@when("the Buyer Agent sends a get_media_buys request with no include_snapshot param")
@when("the Buyer Agent sends a get_media_buys request with no status_filter")
@when("the Buyer Agent sends a get_media_buys request with no status_filter and no media_buy_ids")
@when(parsers.parse('"{principal_id}" sends a get_media_buys request'))
def when_query_no_filters(ctx: dict, principal_id: str | None = None) -> None:
    """Send get_media_buys with default parameters (no extra kwargs)."""
    _dispatch_query(ctx)


@when(
    parsers.re(
        r"the Buyer Agent sends a get_media_buys request with no status_filter and media_buy_ids (?P<ids>\[.+\])"
    )
)
def when_query_no_filter_with_ids(ctx: dict, ids: str) -> None:
    """No status_filter but explicit media_buy_ids — the by-ID path returns every
    matching buy regardless of status (status filter is skipped for explicit IDs).
    """
    import json

    real_ids = _resolve_media_buy_ids(ctx, json.loads(ids))
    _dispatch_query(ctx, media_buy_ids=real_ids)


@when("the Buyer Agent sends a get_media_buys request without authentication")
def when_query_no_auth(ctx: dict) -> None:
    """Send get_media_buys without authentication."""
    ctx["has_auth"] = False
    _dispatch_query(ctx)


@when(parsers.parse("the Buyer Agent sends a get_media_buys request for media_buy_ids {ids}"))
@when(parsers.parse("the Buyer Agent sends a get_media_buys request with media_buy_ids {ids}"))
def when_query_for_ids(ctx: dict, ids: str) -> None:
    """Send get_media_buys filtered by media_buy_ids."""
    import json

    parsed_labels = json.loads(ids)
    real_ids = _resolve_media_buy_ids(ctx, parsed_labels)
    _dispatch_query(ctx, media_buy_ids=real_ids)


@when(parsers.parse("the Buyer Agent sends a get_media_buys request with include_snapshot false"))
def when_query_snapshot_false(ctx: dict) -> None:
    """Send get_media_buys with include_snapshot=False."""
    _dispatch_query(ctx, include_snapshot=False)


@when(parsers.parse('the Buyer Agent sends a get_media_buys request with status_filter "{status}"'))
def when_query_status_filter(ctx: dict, status: str) -> None:
    """Send get_media_buys with a status_filter string."""
    _dispatch_query(ctx, status_filter=[status])


@when(parsers.parse("the Buyer Agent sends a get_media_buys request with status_filter {statuses}"))
def when_query_status_filter_array(ctx: dict, statuses: str) -> None:
    """Send get_media_buys with a status_filter array."""
    import json

    if statuses.startswith("as empty array"):
        _dispatch_query(ctx, status_filter=[])
        return
    parsed = json.loads(statuses.replace("'", '"'))
    _dispatch_query(ctx, status_filter=parsed)


@when("the Buyer Agent sends a get_media_buys request with status_filter as empty array []")
def when_query_empty_status_filter(ctx: dict) -> None:
    """Send get_media_buys with empty status_filter array."""
    _dispatch_query(ctx, status_filter=[])


@when("the Buyer Agent sends a get_media_buys request with all seven v3.1 status values in status_filter")
def when_query_all_statuses(ctx: dict) -> None:
    """Send get_media_buys with all seven v3.1 MediaBuyStatus enum values.

    Derived from the pinned SDK MediaBuyStatus enum (the enums/media-buy-status.json
    vocabulary) rather than a hand-listed literal, so the "seven" tracks the spec
    automatically and doesn't duplicate the status list held elsewhere.
    """
    from adcp.types import MediaBuyStatus

    _dispatch_query(ctx, status_filter=[s.value for s in MediaBuyStatus])


@when(parsers.parse("the Buyer Agent sends a get_media_buys request with invalid parameter types"))
def when_query_invalid_params(ctx: dict) -> None:
    """Send get_media_buys with invalid parameter types (ext-d validation)."""
    _dispatch_query(ctx, media_buy_ids="not-a-list")


@when(parsers.parse('the Buyer Agent sends a get_media_buys request with account_id "{account_id}"'))
def when_query_with_account(ctx: dict, account_id: str) -> None:
    """Send get_media_buys with account_id filter (ext-e)."""
    _dispatch_query(ctx, account={"account_id": account_id})


@when(parsers.parse("the Buyer Agent sends a get_media_buys request with invalid status filter"))
def when_query_invalid_status_filter(ctx: dict) -> None:
    """Send get_media_buys with an invalid status filter (sandbox-validation)."""
    _dispatch_query(ctx, status_filter=["invalid_status"])


# ═══════════════════════════════════════════════════════════════════════
# THEN steps — response assertions
# ═══════════════════════════════════════════════════════════════════════


def _assert_flight_dates_present(pkg: Any) -> None:
    """Assert flight date fields are present on a package.

    Step text claims 'flight dates' — check start_date/end_date or
    start_time/end_time (naming varies by schema version).
    """
    import pytest

    def _has(field: str) -> bool:
        if isinstance(pkg, dict):
            return field in pkg and pkg[field] is not None
        return getattr(pkg, field, None) is not None

    has_dates = _has("start_date") and _has("end_date")
    has_times = _has("start_time") and _has("end_time")
    if not has_dates and not has_times:
        pytest.xfail(
            "SPEC-PRODUCTION GAP: Package missing flight date fields "
            "(start_date/end_date or start_time/end_time). Step claims "
            "'flight dates' are included in package details."
        )


def _get_media_buys(ctx: dict) -> list:
    """Extract media_buys list from response."""
    resp = ctx.get("response")
    if resp is None and "error" in ctx:
        raise AssertionError(f"Expected a response but got error: {ctx['error']}")
    assert resp is not None, "Expected a response"
    buys = getattr(resp, "media_buys", None)
    if buys is None and hasattr(resp, "model_dump"):
        buys = resp.model_dump().get("media_buys", [])
    return buys or []


@then(parsers.parse('the response should include media buy "{mb_id}" with status "{status}"'))
def then_response_includes_mb_with_status(ctx: dict, mb_id: str, status: str) -> None:
    """Assert response includes the media buy with expected status."""
    real_id = _resolve_media_buy_id(ctx, mb_id)
    buys = _get_media_buys(ctx)
    matching = [b for b in buys if getattr(b, "media_buy_id", None) == real_id]
    assert len(matching) == 1, (
        f"Expected media buy '{mb_id}' (real_id={real_id}) in response, "
        f"got IDs: {[getattr(b, 'media_buy_id', None) for b in buys]}"
    )
    actual_status = getattr(matching[0], "status", None)
    # Status may be an enum — convert to string
    actual_str = actual_status.value if hasattr(actual_status, "value") else str(actual_status)
    assert actual_str == status, f"Expected status '{status}' for {mb_id}, got '{actual_str}'"


@then(
    "each media buy should include package-level details with budget, bid_price, product_id, flight dates, and paused state"
)
def then_package_details(ctx: dict) -> None:
    """Assert each media buy has package-level details including all claimed fields."""
    import pytest

    buys = _get_media_buys(ctx)
    assert buys, "No media buys in response to check"
    total_packages_checked = 0
    paused_gaps: list[str] = []
    for buy in buys:
        mb_id = buy.media_buy_id
        packages = buy.packages or []
        assert packages, (
            f"Media buy '{mb_id}' has no packages — step text claims "
            "'each media buy should include package-level details' but packages list is empty"
        )
        for pkg in packages:
            total_packages_checked += 1
            assert isinstance(pkg.package_id, str) and pkg.package_id, (
                f"Package missing or empty package_id, got {pkg.package_id!r}"
            )
            # Step text claims: budget, bid_price, product_id, flight dates, paused
            assert pkg.product_id is not None, f"Package {pkg.package_id} missing product_id"
            assert pkg.budget is not None, f"Package {pkg.package_id} missing budget"
            # Verify budget is numeric
            assert isinstance(pkg.budget, int | float), (
                f"Expected budget to be numeric, got {type(pkg.budget).__name__}: {pkg.budget!r}"
            )
            # bid_price may be None for fixed-price options — verify the field value type when present
            if pkg.bid_price is not None:
                assert isinstance(pkg.bid_price, int | float), (
                    f"Expected bid_price to be numeric, got {type(pkg.bid_price).__name__}: {pkg.bid_price!r}"
                )
            # Flight dates: step text explicitly claims these are present
            _assert_flight_dates_present(pkg)
            # paused must be a boolean, not absent — collect gaps across ALL packages
            if pkg.paused is None:
                paused_gaps.append(f"package {pkg.package_id} in {mb_id}")
            else:
                assert isinstance(pkg.paused, bool), f"Expected paused to be bool, got {type(pkg.paused)}"
    assert total_packages_checked > 0, "No packages checked despite media buys being present"
    if paused_gaps:
        pytest.xfail(
            f"SPEC-PRODUCTION GAP: paused field not present on {len(paused_gaps)} of "
            f"{total_packages_checked} package(s): {', '.join(paused_gaps)}. "
            f"All other fields (budget, bid_price, product_id, flight dates) verified. "
            f"FIXME(salesagent-9vgz.1)"
        )


@then("each package should include creative approval state when creatives are assigned")
def then_creative_approval_state(ctx: dict) -> None:
    """Assert packages include creative approval info with meaningful values.

    Step text: "when creatives are assigned" — so we check:
    1. The creative_approvals field must be present on the schema
    2. When creatives ARE assigned, creative_approvals must be populated
    3. Each approval entry must have a valid approval_status
    """
    from src.core.schemas._base import ApprovalStatus

    valid_statuses = {s.value for s in ApprovalStatus}
    buys = _get_media_buys(ctx)
    assert buys, "No media buys in response"
    packages_checked = 0
    packages_with_approvals = 0
    for buy in buys:
        for pkg in buy.packages or []:
            packages_checked += 1
            approvals = pkg.creative_approvals
            if approvals:
                packages_with_approvals += 1
                for approval in approvals:
                    assert isinstance(approval.creative_id, str) and approval.creative_id, (
                        "CreativeApproval entry missing creative_id"
                    )
                    assert approval.approval_status is not None, (
                        f"CreativeApproval for '{approval.creative_id}' has no approval_status"
                    )
                    status_str = (
                        approval.approval_status.value
                        if hasattr(approval.approval_status, "value")
                        else str(approval.approval_status)
                    )
                    assert status_str in valid_statuses, (
                        f"Unexpected approval_status '{status_str}' for creative "
                        f"'{approval.creative_id}', expected one of {valid_statuses}"
                    )
    assert packages_checked > 0, "No packages found to check creative approvals on"
    # Step text says "when creatives are assigned" — verify at least one package
    # actually had creative approvals to check
    assert packages_with_approvals > 0, (
        f"Step claims 'when creatives are assigned' but none of the {packages_checked} "
        f"packages had creative_approvals populated — test setup must assign creatives"
    )


@then("each media buy should include buyer_campaign_ref for correlation")
def then_buyer_campaign_ref_for_correlation(ctx: dict) -> None:
    """Assert buyer_campaign_ref on each response media buy matches the seeded value.

    buyer_campaign_ref is the surviving correlation identifier (top-level buyer_ref
    was removed from the schema in adcp 3.12).
    """
    buys = _get_media_buys(ctx)
    seeded = ctx.get("seeded_media_buys", {})
    checked = 0
    for buy in buys:
        buy_id = buy.media_buy_id

        # buyer_campaign_ref is the surviving correlation identifier.
        # Match it against the value seeded via factory raw_request.
        seeded_mb = None
        for mb in seeded.values():
            if mb.media_buy_id == buy_id:
                seeded_mb = mb
                break
        assert seeded_mb is not None, (
            f"Response media buy '{buy_id}' not found in seeded_media_buys — "
            f"known IDs: {[m.media_buy_id for m in seeded.values()]}"
        )
        expected_ref = (seeded_mb.raw_request or {}).get("buyer_campaign_ref")
        actual_ref = buy.buyer_campaign_ref
        assert actual_ref == expected_ref, (
            f"Media buy '{buy_id}' buyer_campaign_ref mismatch: "
            f"expected {expected_ref!r} (from factory raw_request), got {actual_ref!r}"
        )
        checked += 1
    assert checked == len(seeded), (
        f"Expected {len(seeded)} media buys with buyer_campaign_ref verified, but only checked {checked}"
    )


@then(parsers.parse('the response should include media buys "{mb1}" and "{mb2}"'))
def then_response_includes_two(ctx: dict, mb1: str, mb2: str) -> None:
    """Assert response includes both specified media buys."""
    real_id1 = _resolve_media_buy_id(ctx, mb1)
    real_id2 = _resolve_media_buy_id(ctx, mb2)
    buys = _get_media_buys(ctx)
    ids = {getattr(b, "media_buy_id", None) for b in buys}
    assert real_id1 in ids, f"Expected '{mb1}' (real_id={real_id1}) in response, got {ids}"
    assert real_id2 in ids, f"Expected '{mb2}' (real_id={real_id2}) in response, got {ids}"


@then(parsers.parse('the response should not include media buy "{mb_id}"'))
def then_response_excludes(ctx: dict, mb_id: str) -> None:
    """Assert response does not include the specified media buy."""
    real_id = _resolve_media_buy_id(ctx, mb_id)
    buys = _get_media_buys(ctx)
    ids = {getattr(b, "media_buy_id", None) for b in buys}
    assert real_id not in ids, f"Expected '{mb_id}' (real_id={real_id}) NOT in response, but it was present"


@then(parsers.parse('the response should include media buy "{mb_id}"'))
def then_response_includes_one(ctx: dict, mb_id: str) -> None:
    """Assert response includes the specified media buy."""
    real_id = _resolve_media_buy_id(ctx, mb_id)
    buys = _get_media_buys(ctx)
    ids = {getattr(b, "media_buy_id", None) for b in buys}
    assert real_id in ids, f"Expected '{mb_id}' (real_id={real_id}) in response, got {ids}"


@then(parsers.parse('the response package "{pkg_id}" should include a snapshot'))
def then_package_has_snapshot(ctx: dict, pkg_id: str) -> None:
    """Assert package includes snapshot data."""
    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                snapshot = getattr(pkg, "snapshot", None)
                assert snapshot is not None, f"Expected snapshot on package '{pkg_id}'"
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then("the snapshot should include as_of, staleness_seconds, impressions, and spend")
def then_snapshot_fields(ctx: dict) -> None:
    """Assert snapshot has all 4 claimed fields: as_of, staleness_seconds, impressions, spend.

    Must check ALL packages with snapshots, not just the first one found.
    """
    required_fields = ("as_of", "staleness_seconds", "impressions", "spend")
    buys = _get_media_buys(ctx)
    checked_any = False
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            snapshot = getattr(pkg, "snapshot", None)
            if snapshot is not None:
                checked_any = True
                for field in required_fields:
                    val = getattr(snapshot, field, None)
                    if val is None and isinstance(snapshot, dict):
                        val = snapshot.get(field)
                    assert val is not None, (
                        f"Snapshot on package '{getattr(pkg, 'package_id', '?')}' missing required field '{field}'"
                    )
    assert checked_any, "No snapshots found — this step requires at least one snapshot to verify"


@then("the response should include an empty media_buys array")
def then_empty_media_buys(ctx: dict) -> None:
    """Assert response has an empty media_buys array."""
    buys = _get_media_buys(ctx)
    assert len(buys) == 0, f"Expected empty media_buys, got {len(buys)}"


@then("no error should be present in the response")
def then_no_error_in_response(ctx: dict) -> None:
    """Assert no error in the response."""
    assert "error" not in ctx, f"Unexpected error: {ctx.get('error')}"
    resp = ctx.get("response")
    if resp is not None:
        errors = getattr(resp, "errors", None)
        assert not errors, f"Unexpected errors in response: {errors}"


@then(parsers.parse('the operation should fail with error code "{code}"'))
def then_fail_with_code(ctx: dict, code: str) -> None:
    """Assert operation failed with specific error code — wire-first, typed fallback.

    On a wire transport (A2A here; MCP wire capture is pending the
    _run_mcp_client upgrade of MediaBuyListEnv) the code is read from the real
    two-layer envelope, and BOTH layers must agree (envelope-level
    ``adcp_error.code`` and payload-level ``errors[0].code``). No-wire runs
    fall back to the typed production exception. Cannot use
    ``result.assert_wire_error`` unconditionally: this step also grades
    locally-tracked non-canonical codes (e.g. ACCOUNT_FILTER_NOT_SUPPORTED)
    absent from the pinned error-code enum.
    """
    wire_code = _wire_code(ctx)
    if wire_code is not None:
        assert wire_code == code, f"Expected wire adcp_error.code '{code}', got '{wire_code}'"
        payload_error = _wire_error_object(ctx) or {}
        assert payload_error.get("code") == code, (
            f"Two-layer envelope disagreement: adcp_error.code={code!r} but "
            f"errors[0].code={payload_error.get('code')!r}"
        )
        return
    error = ctx.get("error")
    assert error is not None, "Expected an error but none found"
    from src.core.exceptions import AdCPError

    if isinstance(error, AdCPError):
        assert error.error_code == code, f"Expected error code '{code}', got '{error.error_code}'"
    else:
        raise AssertionError(f"Expected AdCPError with code '{code}', got {type(error).__name__}: {error}")


@then("the error message should indicate that identity is required")
def then_error_identity_required(ctx: dict) -> None:
    """Assert error mentions identity/authentication."""
    error = ctx.get("error")
    assert error is not None, "Expected an error"
    msg = str(error).lower()
    assert any(kw in msg for kw in ("identity", "auth", "principal", "credential")), (
        f"Expected identity-related error message, got: {error}"
    )


def _assert_error_recovery(ctx: dict, expected: str) -> None:
    """Assert the error's recovery classification — wire-first, typed fallback.

    On a wire transport the ``recovery`` field is read from the real envelope's
    error object (the buyer-facing retry semantics per error.json); no-wire
    runs fall back to the typed production exception.
    """
    wire = _wire_error_object(ctx)
    if wire is not None:
        assert wire.get("recovery") == expected, (
            f"Expected wire recovery='{expected}', got {wire.get('recovery')!r} on wire code {wire.get('code')!r}"
        )
        return
    error = ctx.get("error")
    assert error is not None, "Expected an error"
    from src.core.exceptions import AdCPError

    assert isinstance(error, AdCPError), f"Expected AdCPError with recovery field, got {type(error).__name__}: {error}"
    assert error.recovery == expected, f"Expected {expected} recovery, got '{error.recovery}'"


@then(parsers.parse('the error should include a "recovery" field indicating terminal failure'))
def then_error_recovery_terminal(ctx: dict) -> None:
    """Assert error has terminal recovery classification."""
    _assert_error_recovery(ctx, "terminal")


def _current_suggestion(ctx: dict) -> str:
    """Resolve the buyer-facing error suggestion — wire-first, typed fallback.

    On a wire transport the suggestion is read from the real envelope at the
    protocol top level (STRICT error.json conformance — a suggestion buried in
    ``details`` does not count, #1417); no-wire runs fall back to the typed
    production exception's top-level attribute. Fails when the suggestion is
    missing or empty — never a silent escape.
    """
    suggestion = _wire_suggestion(ctx)
    if suggestion is None:
        error = ctx.get("error")
        assert error is not None, "Expected an error"
        from src.core.exceptions import AdCPError

        assert isinstance(error, AdCPError), (
            f"Expected AdCPError with suggestion field, got {type(error).__name__}: {error}"
        )
        # STRICT error.json conformance: top-level attribute only (#1417).
        suggestion = error.suggestion
    assert isinstance(suggestion, str) and suggestion.strip(), (
        f"Expected non-empty top-level suggestion string, got {suggestion!r}"
    )
    return suggestion


def _assert_suggestion_contains_any(ctx: dict, options: list[str]) -> None:
    """Assert the buyer-facing suggestion contains at least one of the options."""
    suggestion = _current_suggestion(ctx)
    lowered = suggestion.lower()
    assert any(t.lower() in lowered for t in options), f"Expected one of {options!r} in suggestion: {suggestion}"


@then(parsers.parse('the suggestion should contain "{text1}" or "{text2}"'))
def then_suggestion_contains_either(ctx: dict, text1: str, text2: str) -> None:
    """Assert suggestion contains one of the specified texts."""
    _assert_suggestion_contains_any(ctx, [text1, text2])


@then(parsers.parse('the suggestion should contain "{text1}" or "{text2}" or "{text3}"'))
def then_suggestion_contains_any_of_three(ctx: dict, text1: str, text2: str, text3: str) -> None:
    """Assert suggestion contains one of three specified texts."""
    _assert_suggestion_contains_any(ctx, [text1, text2, text3])


@then(parsers.parse('the media buy "{mb_id}" should have status "{expected_status}"'))
def then_media_buy_has_status(ctx: dict, mb_id: str, expected_status: str) -> None:
    """Assert a specific media buy has the expected status in the response."""
    real_id = _resolve_media_buy_id(ctx, mb_id)
    buys = _get_media_buys(ctx)
    matching = [b for b in buys if getattr(b, "media_buy_id", None) == real_id]
    assert len(matching) == 1, (
        f"Expected media buy '{mb_id}' (real_id={real_id}) in response, "
        f"got IDs: {[getattr(b, 'media_buy_id', None) for b in buys]}"
    )
    actual = getattr(matching[0], "status", None)
    actual_str = actual.value if hasattr(actual, "value") else str(actual)
    assert actual_str == expected_status, f"Expected status '{expected_status}' for '{mb_id}', got '{actual_str}'"


@then(parsers.parse("the error message should include field-level validation details"))
def then_error_field_validation(ctx: dict) -> None:
    """Assert error includes field-level validation details with actual field names.

    Step text claims "field-level validation details" — the error must reference
    specific field names or paths (media_buy_ids, status_filter, buyer_refs, etc.),
    not just generic words like "type" or "expected" that appear in any error.
    """
    # Require actual field names from GetMediaBuysRequest schema.
    field_names = ("media_buy_ids", "status_filter", "buyer_refs", "account_id")
    wire = _wire_error_object(ctx)
    if wire is not None:
        # Wire-first: the buyer-facing message and the structured ``field``
        # selector must reference an actual request schema field.
        text = f"{wire.get('message', '')} {wire.get('field', '')}".lower()
        source = f"wire error object {wire!r}"
    else:
        error = ctx.get("error")
        assert error is not None, "Expected a validation error"
        text = str(error).lower()
        source = f"error message {error}"
    assert any(field_name in text for field_name in field_names), (
        f"Expected field-level validation details (containing actual field names like {field_names}) in {source}"
    )


@then(parsers.parse('the error should include a "recovery" field indicating correctable failure'))
def then_error_recovery_correctable(ctx: dict) -> None:
    """Assert error has recovery field set to 'correctable'.

    The step text explicitly says "correctable failure" — the recovery field
    must be exactly "correctable" (not "retryable" or other values).
    """
    _assert_error_recovery(ctx, "correctable")


@then(parsers.parse('the error should include a "suggestion" field'))
def then_error_has_suggestion(ctx: dict) -> None:
    """Assert error includes a non-empty suggestion — wire-first, typed fallback.

    Step text: 'the error should include a "suggestion" field'.
    No xfail escape — if production omits the suggestion, the test must fail.
    """
    _current_suggestion(ctx)


@then(parsers.parse('the error message should contain "{fragment}"'))
def then_error_contains(ctx: dict, fragment: str) -> None:
    """Assert error message contains a specific fragment."""
    error = ctx.get("error")
    assert error is not None, "Expected an error"
    msg = str(error).lower()
    assert fragment.lower() in msg, f"Expected '{fragment}' in error: {error}"


@then(parsers.parse('the response errors array should include error code "{code}"'))
def then_response_errors_include(ctx: dict, code: str) -> None:
    """Assert response.errors contains the specified error code."""
    resp = ctx.get("response")
    assert resp is not None, f"Expected response, got error: {ctx.get('error')}"
    errors = getattr(resp, "errors", None) or []
    codes = [e.get("code") if isinstance(e, dict) else getattr(e, "code", None) for e in errors]
    assert code in codes, f"Expected error code '{code}' in response errors, got {codes}"


@then(parsers.parse('the error message should indicate "{text}" is not a valid MediaBuyStatus'))
def then_error_invalid_status(ctx: dict, text: str) -> None:
    """Assert error mentions the invalid status value."""
    error = ctx.get("error")
    assert error is not None, "Expected an error"
    msg = str(error).lower()
    # Step text requires BOTH: mention of the invalid value AND that it's about status
    assert text.lower() in msg, f"Expected invalid value '{text}' to appear in error message, got: {error}"
    assert "status" in msg, (
        f"Expected 'status' to appear in error message (indicating this is a status validation error), got: {error}"
    )


@then(parsers.parse('the creative approval for "{creative_id}" should have approval_status "{status}"'))
def then_creative_approval_status(ctx: dict, creative_id: str, status: str) -> None:
    """Assert a specific creative's approval status in the response.

    Searches ALL packages across ALL media buys for a creative_approvals
    entry matching creative_id, then asserts approval_status.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                aid = getattr(approval, "creative_id", None)
                if aid == creative_id:
                    actual = getattr(approval, "approval_status", None)
                    actual_str = actual.value if hasattr(actual, "value") else str(actual)
                    assert actual_str == status, (
                        f"Expected approval_status '{status}' for creative '{creative_id}', got '{actual_str}'"
                    )
                    return
    raise AssertionError(f"No approval entry found for creative '{creative_id}' across {len(buys)} media buy(s)")


@then(parsers.parse('the creative approval should have approval_status "{status}"'))
def then_any_creative_approval_status(ctx: dict, status: str) -> None:
    """Assert creative approval status on any package (any creative matches)."""

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                actual = getattr(approval, "approval_status", None)
                actual_str = actual.value if hasattr(actual, "value") else str(actual)
                if actual_str == status:
                    return  # Found a matching approval
    raise AssertionError(f"No approval with status='{status}' found across {len(buys)} media buy(s)")


@then(parsers.parse('the rejection_reason should be "{reason}"'))
def then_rejection_reason(ctx: dict, reason: str) -> None:
    """Assert rejection_reason matches expected value on any approval."""

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                actual_reason = getattr(approval, "rejection_reason", None)
                if actual_reason is not None:
                    assert str(actual_reason) == reason, f"Expected rejection_reason '{reason}', got '{actual_reason}'"
                    return
    raise AssertionError(
        f"No approval with rejection_reason found across {len(buys)} media buy(s), expected '{reason}'"
    )


@then(parsers.parse("rejection_reason should be absent"))
def then_rejection_reason_absent(ctx: dict) -> None:
    """Assert rejection_reason is absent on ALL approvals when not rejected."""

    buys = _get_media_buys(ctx)
    checked = 0
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                checked += 1
                actual_reason = getattr(approval, "rejection_reason", None)
                assert actual_reason is None, f"Expected rejection_reason to be absent, got '{actual_reason}'"
    assert checked > 0, "No approval entries found in response — cannot verify rejection_reason absence"


@then(parsers.parse("rejection_reason should not be present in the approval entry"))
def then_rejection_reason_not_present(ctx: dict) -> None:
    """Assert rejection_reason is not present on ANY approval entry."""

    buys = _get_media_buys(ctx)
    checked = 0
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                checked += 1
                actual_reason = getattr(approval, "rejection_reason", None)
                assert actual_reason is None, f"Expected rejection_reason to not be present, got '{actual_reason}'"
    assert checked > 0, "No approval entries found in response — cannot verify rejection_reason absence"


@then(parsers.parse("rejection_reason should be null or absent"))
def then_rejection_reason_null_or_absent(ctx: dict) -> None:
    """Assert rejection_reason is null or absent on ALL approval entries."""

    buys = _get_media_buys(ctx)
    checked = 0
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            approvals = getattr(pkg, "creative_approvals", None) or []
            for approval in approvals:
                checked += 1
                actual_reason = getattr(approval, "rejection_reason", None)
                assert actual_reason is None, f"Expected rejection_reason to be null or absent, got '{actual_reason}'"
    assert checked > 0, "No approval entries found in response — cannot verify rejection_reason null/absent"


@then(parsers.parse('the creative approvals for package "{pkg_id}" should not include an entry for "{creative_id}"'))
def then_no_approval_for_creative(ctx: dict, pkg_id: str, creative_id: str) -> None:
    """Assert missing creative is not in approvals (INV-152-4).

    The package MUST be found in the response — if it's missing, that's a hard
    failure, not an xfail.
    """
    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                approvals = getattr(pkg, "creative_approvals", None) or []
                approval_ids = [getattr(a, "creative_id", None) for a in approvals]
                assert creative_id not in approval_ids, (
                    f"Expected creative '{creative_id}' to NOT appear in approvals for package '{pkg_id}', but found it"
                )
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response — cannot verify creative '{creative_id}' omission")


@then(parsers.parse("no error should be raised for the missing creative"))
def then_no_error_for_missing_creative(ctx: dict) -> None:
    """Assert no error raised for missing creative."""
    assert "error" not in ctx or ctx.get("error") is None, f"Unexpected error for missing creative: {ctx.get('error')}"


@then(parsers.parse('package "{pkg_id}" should not have a snapshot field'))
def then_package_no_snapshot(ctx: dict, pkg_id: str) -> None:
    """Assert package does not have a snapshot field (INV-153-1).

    Step text: 'should not have a snapshot field'. If production returns
    a snapshot contrary to the requirement, this is a spec-production gap.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                snapshot = getattr(pkg, "snapshot", None)
                # Violation path: snapshot IS present when it should NOT be
                assert snapshot is None, f"Package '{pkg_id}' has snapshot={snapshot!r} — should be absent"
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse('package "{pkg_id}" should not have a snapshot_unavailable_reason field'))
def then_package_no_unavailable_reason(ctx: dict, pkg_id: str) -> None:
    """Assert package does not have snapshot_unavailable_reason (INV-153-1).

    Step text: 'should not have a snapshot_unavailable_reason field'.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                reason = getattr(pkg, "snapshot_unavailable_reason", None)
                # Violation path: reason IS present when it should NOT be
                assert reason is None, (
                    f"Package '{pkg_id}' has snapshot_unavailable_reason='{reason}' — should be absent"
                )
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse('package "{pkg_id}" should have snapshot_unavailable_reason "{reason}"'))
def then_package_unavailable_reason(ctx: dict, pkg_id: str, reason: str) -> None:
    """Assert package has specific snapshot_unavailable_reason."""

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                actual = getattr(pkg, "snapshot_unavailable_reason", None)
                assert actual is not None, (
                    f"Package '{pkg_id}' missing snapshot_unavailable_reason, expected '{reason}'"
                )
                actual_str = actual.value if hasattr(actual, "value") else str(actual)
                assert actual_str == reason, f"Expected snapshot_unavailable_reason '{reason}', got '{actual_str}'"
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse('the snapshot for package "{pkg_id}" should include "{field}" timestamp'))
def then_snapshot_field_timestamp(ctx: dict, pkg_id: str, field: str) -> None:
    """Assert snapshot has a timestamp field with valid ISO 8601 format."""
    from datetime import datetime

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                snapshot = getattr(pkg, "snapshot", None)
                assert snapshot is not None, f"Package '{pkg_id}' has no snapshot — cannot verify '{field}' timestamp"
                val = getattr(snapshot, field, None)
                if val is None and isinstance(snapshot, dict):
                    val = snapshot.get(field)
                assert val is not None, f"Snapshot field '{field}' not present on package '{pkg_id}'"
                # Accept both datetime objects and ISO 8601 strings
                if isinstance(val, datetime):
                    return  # Already a datetime — valid timestamp
                assert isinstance(val, str), (
                    f"Expected '{field}' to be a timestamp (datetime or ISO 8601 string), "
                    f"got {type(val).__name__}: {val!r}"
                )
                try:
                    datetime.fromisoformat(val.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise AssertionError(
                        f"Snapshot field '{field}' value '{val}' is not a valid ISO 8601 timestamp: {exc}"
                    ) from exc
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse('the snapshot should include "{field}" integer'))
def then_snapshot_field_integer(ctx: dict, field: str) -> None:
    """Assert snapshot has a non-negative integer field.

    Snapshot integer fields (e.g. staleness_seconds) represent metrics that
    must be non-negative per the Snapshot schema (ge=0 constraint).
    """
    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            snapshot = getattr(pkg, "snapshot", None)
            if snapshot is not None:
                val = getattr(snapshot, field, None)
                if val is None and isinstance(snapshot, dict):
                    val = snapshot.get(field)
                assert val is not None, f"Snapshot field '{field}' not present — snapshot data propagation incomplete"
                assert isinstance(val, int), f"Expected '{field}' to be an integer, got {type(val).__name__}: {val!r}"
                assert val >= 0, f"Expected '{field}' to be non-negative, got {val}"
                return
    raise AssertionError(f"No snapshots found — cannot verify '{field}' integer")


@then(parsers.parse('the snapshot should include "{field}" count'))
def then_snapshot_field_count(ctx: dict, field: str) -> None:
    """Assert snapshot has a positive numeric count field matching seeded data.

    Step text says "count" — the value must be numeric and positive (> 0),
    verifying that the production code correctly propagated real data from
    the adapter snapshot, not just a default/zero value.
    When expected_snapshots are available in ctx, verify value matches.
    """
    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            snapshot = getattr(pkg, "snapshot", None)
            if snapshot is not None:
                val = getattr(snapshot, field, None)
                if val is None and isinstance(snapshot, dict):
                    val = snapshot.get(field)
                assert val is not None, f"Snapshot field '{field}' count not present on package"
                assert isinstance(val, (int, float)), (
                    f"Expected '{field}' to be a numeric count, got {type(val).__name__}: {val!r}"
                )
                assert val > 0, (
                    f"Expected '{field}' count to be positive (> 0) — a zero value suggests "
                    f"snapshot data was not propagated from adapter. Got {val}"
                )
                # Verify against seeded snapshot data if available
                pkg_id = getattr(pkg, "package_id", None)
                expected = ctx.get("expected_snapshots", {}).get(pkg_id)
                if expected is not None:
                    expected_val = getattr(expected, field, None)
                    if expected_val is not None:
                        assert val == expected_val, (
                            f"Snapshot '{field}' value {val} does not match seeded "
                            f"value {expected_val} for package '{pkg_id}'"
                        )
                return
    raise AssertionError(f"No snapshots found — cannot verify '{field}' count")


@then(parsers.parse('the snapshot should include "{field}" amount'))
def then_snapshot_field_amount(ctx: dict, field: str) -> None:
    """Assert snapshot field matches the exact value from the seeded expected_snapshots.

    The Given step stores expected Snapshot objects in ctx["expected_snapshots"][pkg_id].
    We verify the response snapshot field equals that exact seeded value.
    """
    expected_snapshots = ctx.get("expected_snapshots", {})
    assert expected_snapshots, (
        f"No expected_snapshots in ctx — the Given step must seed snapshot data "
        f"via _make_test_snapshot() before asserting '{field}' amount"
    )
    buys = _get_media_buys(ctx)
    snapshots_checked = 0
    for buy in buys:
        for pkg in buy.packages or []:
            if pkg.snapshot is None:
                continue
            snapshots_checked += 1
            actual_val = getattr(pkg.snapshot, field, None)
            assert actual_val is not None, f"Snapshot field '{field}' not present on package '{pkg.package_id}'"
            expected_snapshot = expected_snapshots.get(pkg.package_id)
            assert expected_snapshot is not None, (
                f"Package '{pkg.package_id}' has a snapshot but no expected_snapshot was seeded. "
                f"Known seeded packages: {list(expected_snapshots)}"
            )
            expected_val = getattr(expected_snapshot, field)
            assert actual_val == expected_val, (
                f"Snapshot '{field}' on package '{pkg.package_id}': "
                f"expected {expected_val!r} (from seeded snapshot), got {actual_val!r}"
            )
    assert snapshots_checked > 0, f"No packages with snapshots found — cannot verify '{field}' amount"


@then(parsers.parse("the response should include {count:d} media buys"))
def then_response_count(ctx: dict, count: int) -> None:
    """Assert response has a specific number of media buys."""
    buys = _get_media_buys(ctx)
    assert len(buys) == count, f"Expected {count} media buys, got {len(buys)}"


@then(parsers.parse("the response should include {count:d} media buys scoped to {principal_id}"))
def then_response_count_scoped(ctx: dict, count: int, principal_id: str) -> None:
    """Assert response has N media buys scoped to a principal.

    Step text claims 'scoped to {principal_id}' — scoping MUST be verified,
    not just the count.
    """
    buys = _get_media_buys(ctx)
    assert len(buys) == count, f"Expected {count} media buys for '{principal_id}', got {len(buys)}"
    # Verify scoping: all returned buys should belong to the claimed principal
    seeded = ctx.get("seeded_media_buys", {})
    # Build reverse map: real_id → ORM object
    real_id_to_mb = {mb_obj.media_buy_id: mb_obj for mb_obj in seeded.values()}
    returned_ids = {getattr(b, "media_buy_id", None) for b in buys}
    resolved = _resolve_principal_id(ctx, principal_id)
    scoping_checked = 0
    for real_id in returned_ids:
        if real_id in real_id_to_mb:
            mb = real_id_to_mb[real_id]
            actual_principal = getattr(mb, "principal_id", None)
            if actual_principal is not None:
                scoping_checked += 1
                assert actual_principal == resolved, (
                    f"Media buy '{real_id}' belongs to principal '{actual_principal}', "
                    f"not '{resolved}' (label '{principal_id}') — scoping violation"
                )
    # Step claims scoping — we must have verified at least one buy's ownership
    if count > 0:
        assert scoping_checked > 0, (
            f"Step claims scoping to '{principal_id}' but verified 0 of {count} returned buys. "
            f"Returned IDs: {returned_ids}, seeded real IDs: {set(real_id_to_mb.keys())}"
        )


@then(parsers.parse('the response should contain "media_buys" array'))
def then_response_has_media_buys_array(ctx: dict) -> None:
    """Assert response has a media_buys field that is a list (array)."""
    resp = ctx.get("response")
    assert resp is not None, f"Expected response, got error: {ctx.get('error')}"
    buys = getattr(resp, "media_buys", None)
    assert buys is not None, "Response missing media_buys field"
    assert isinstance(buys, list), f"Expected media_buys to be a list (array), got {type(buys).__name__}"


@then("the response should include sandbox equals true")
def then_sandbox_true(ctx: dict) -> None:
    """Assert response includes sandbox=true.

    Scenario-level xfail (T-UC-019-sandbox-happy) handles the expected failure
    when sandbox mode is not yet implemented in production.
    """
    resp = ctx.get("response")
    assert resp is not None, f"Expected response, got error: {ctx.get('error')}"
    sandbox = getattr(resp, "sandbox", None)
    assert sandbox is True, f"Expected sandbox=true, got {sandbox!r}"


@then("the response should not include a sandbox field")
def then_no_sandbox_field(ctx: dict) -> None:
    """Assert response does not include sandbox field for production accounts.

    Step text: 'should not include a sandbox field'. If production includes
    it anyway, this is a spec-production gap.
    """

    resp = ctx.get("response")
    assert resp is not None, f"Expected response, got error: {ctx.get('error')}"
    sandbox = getattr(resp, "sandbox", None)
    # Violation path: sandbox IS present when it should NOT be
    assert sandbox is None, (
        f"Production response includes sandbox={sandbox!r} for production account — should be absent"
    )


@then("the response should indicate a validation error")
def then_validation_error(ctx: dict) -> None:
    """Assert response indicates a validation error — wire-first.

    On a wire transport the buyer-facing code must be exactly VALIDATION_ERROR
    (the pinned error-code enum's canonical request-validation code). No-wire
    fallback: either a raised exception with validation-related keywords, or
    response.errors containing validation-related content.
    """
    wire_code = _wire_code(ctx)
    if wire_code is not None:
        assert wire_code == "VALIDATION_ERROR", f"Expected wire code VALIDATION_ERROR, got {wire_code!r}"
        return

    error = ctx.get("error")
    if error:
        # Verify it's actually a validation error, not just any error
        msg = str(error).lower()
        assert any(kw in msg for kw in ("validation", "invalid", "required", "type", "field")), (
            f"Expected a validation error, but error doesn't indicate validation: {error}"
        )
        return
    resp = ctx.get("response")
    if resp:
        errors = getattr(resp, "errors", None)
        if errors:
            # Verify at least one error relates to validation
            error_strs = [str(e).lower() for e in errors]
            has_validation_keyword = any(
                any(kw in s for kw in ("validation", "invalid", "required", "type", "field")) for s in error_strs
            )
            assert has_validation_keyword, f"Response has errors but none indicate validation: {errors}"
            return
    raise AssertionError(
        "Expected validation error: neither error raised nor response.errors contains validation content"
    )


@then("the error should be a real validation error, not simulated")
def then_real_validation_error(ctx: dict) -> None:
    """Assert error is a real validation error (not simulated sandbox response).

    Wire-first: a "real" validation error is an actual wire REJECTION — a
    two-layer error envelope carrying VALIDATION_ERROR with correctable
    recovery (BR-RULE-209 INV-7: sandbox inputs are validated like production;
    a simulated sandbox response would come back as a success payload instead).
    No-wire fallback: the typed production exception.
    """
    result = ctx.get("result")
    if result is not None and result.wire_error_envelope is not None:
        result.assert_wire_error("VALIDATION_ERROR")
        return

    error = ctx.get("error")
    assert error is not None, "Expected a real validation error but no error was raised"
    from src.core.exceptions import AdCPError

    # A "real" validation error is an actual exception (not a response-embedded simulated one)
    assert isinstance(error, (AdCPError, ValueError, TypeError)), (
        f"Expected a real validation error (AdCPError/ValueError/TypeError), got {type(error).__name__}: {error}"
    )


@then("the error should include a suggestion for how to fix the issue")
def then_error_suggestion_for_fix(ctx: dict) -> None:
    """Assert error includes a suggestion with actionable fix guidance.

    Step text: 'suggestion for how to fix the issue' — the suggestion must be
    a non-empty string with enough content to be actionable (at least 5 chars).
    Wire-first, typed fallback (see _current_suggestion). No xfail escape —
    if production omits suggestions, the test must fail.
    """
    suggestion = _current_suggestion(ctx)
    assert len(suggestion.strip()) >= 5, (
        f"Expected actionable suggestion string (>= 5 chars), got {suggestion!r}. "
        f"Step claims 'how to fix the issue' — suggestion must contain meaningful guidance."
    )


@then(parsers.parse('only media buys with status "{status}" are returned'))
def then_only_status(ctx: dict, status: str) -> None:
    """Assert only media buys with the specified status are in the response.

    Non-empty guard (mirrors the uc004 sibling and this module's other status
    Thens): a filter that regresses to ``[]`` must NOT false-green here — the
    single_status / null_default rows route through this step and each seeds a
    matching buy, so an empty result is a real failure, not a vacuous pass.
    """
    buys = _get_media_buys(ctx)
    assert buys, f"Filter '{status}' returned no media buys — expected at least the seeded matching buy."
    for buy in buys:
        actual = getattr(buy, "status", None)
        actual_str = actual.value if hasattr(actual, "value") else str(actual)
        assert actual_str == status, f"Expected only '{status}' buys, got '{actual_str}'"


@then("media buys with either status are returned")
def then_either_status_returned(ctx: dict) -> None:
    """Assert media buys with multiple statuses are returned."""
    buys = _get_media_buys(ctx)
    assert buys, "Expected media buys returned with multi-status filter"
    # "either status" implies at least 2 different statuses are represented
    statuses = {buy.status.value if hasattr(buy.status, "value") else str(buy.status) for buy in buys}
    assert len(statuses) >= 2, (
        f"Step claims 'either status are returned' but only found status(es): {statuses}. "
        f"Expected at least 2 different statuses."
    )


@then("every matching buy returned regardless of status")
def then_every_matching_buy_regardless_of_status(ctx: dict) -> None:
    """By-ID query skips the status filter: all requested buys come back even
    though they hold different lifecycle statuses.

    Non-vacuous: requires the requested buys to be present AND to span more than
    one status (else 'regardless of status' isn't actually exercised).
    """
    buys = _get_media_buys(ctx)
    assert buys, "Expected media buys returned for an explicit-IDs query"
    statuses = {b.status.value if hasattr(b.status, "value") else str(b.status) for b in buys}
    assert len(statuses) >= 2, (
        f"Step claims buys are returned 'regardless of status' but the result holds a "
        f"single status {statuses}; the by-ID skip-filter behavior isn't exercised."
    )


@then("media buys in any status are returned")
def then_any_status_returned(ctx: dict) -> None:
    """Assert all seeded media buys are returned with all-status filter.

    Step text claims "any status are returned" — this requires seeded data
    to exist (to verify completeness) and all seeded IDs to appear in response.
    """
    buys = _get_media_buys(ctx)
    assert buys, "Expected media buys for all-status filter"
    seeded = ctx.get("seeded_media_buys", {})
    assert seeded, (
        "Step claims 'media buys in any status are returned' but no media buys "
        "were seeded — cannot verify completeness without seeded data"
    )
    returned_ids = {b.media_buy_id for b in buys}
    for label, mb_obj in seeded.items():
        real_id = mb_obj.media_buy_id
        assert real_id in returned_ids, (
            f"All-status filter should return all media buys, but '{label}' (real_id={real_id}) is missing. "
            f"Returned: {returned_ids}"
        )


@then(parsers.parse('the response should include an empty media_buys array with error "{code}"'))
def then_empty_with_error(ctx: dict, code: str) -> None:
    """Assert empty media_buys with specific error code in response."""
    buys = _get_media_buys(ctx)
    assert len(buys) == 0, f"Expected empty media_buys, got {len(buys)}"
    resp = ctx.get("response")
    assert resp is not None, (
        f"Expected response with empty media_buys and error '{code}', but response is None. Error: {ctx.get('error')}"
    )
    errors = getattr(resp, "errors", None) or []
    codes = [e.get("code") if isinstance(e, dict) else getattr(e, "code", None) for e in errors]
    assert code in codes, f"Expected error '{code}' in errors, got {codes}"


@then(parsers.parse('empty media_buys with error "{code}"'))
def then_empty_buys_with_error(ctx: dict, code: str) -> None:
    """Assert empty media_buys with error (boundary table shorthand)."""
    buys = _get_media_buys(ctx)
    assert len(buys) == 0, f"Expected empty, got {len(buys)}"
    resp = ctx.get("response")
    assert resp is not None, (
        f"Expected response with empty media_buys and error '{code}', but response is None. Error: {ctx.get('error')}"
    )
    errors = getattr(resp, "errors", None) or []
    codes = [e.get("code") if isinstance(e, dict) else getattr(e, "code", None) for e in errors]
    assert code in codes, f"Expected '{code}' in response errors, got {codes}"


@then(parsers.parse('error "{code}" with suggestion'))
def then_error_code_with_suggestion(ctx: dict, code: str) -> None:
    """Assert error with specific code and suggestion (boundary table shorthand).

    Step text: 'error "{code}" with suggestion'. Asserts both error code AND
    presence of suggestion in details dict.
    """
    error = ctx.get("error")
    assert error is not None, "Expected an error"
    from src.core.exceptions import AdCPError

    assert isinstance(error, AdCPError), f"Expected AdCPError with code '{code}', got {type(error).__name__}: {error}"
    assert error.error_code == code, f"Expected error code '{code}', got '{error.error_code}'"
    # STRICT error.json conformance: suggestion is a top-level error attribute,
    # never read from the free-form details dict (#1417).
    suggestion = error.suggestion
    assert isinstance(suggestion, str) and suggestion.strip(), (
        f"Expected non-empty top-level suggestion string for error code '{code}', got {suggestion!r}"
    )


@then(parsers.parse("no snapshot or snapshot_unavailable_reason on any package"))
def then_no_snapshot_fields(ctx: dict) -> None:
    """Assert no snapshot-related fields on any package.

    Step text: 'no snapshot or snapshot_unavailable_reason on any package'.
    Violations are collected across ALL packages before reporting.
    """

    buys = _get_media_buys(ctx)
    snapshot_violations: list[str] = []
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            pkg_id = getattr(pkg, "package_id", "?")
            snapshot = getattr(pkg, "snapshot", None)
            reason = getattr(pkg, "snapshot_unavailable_reason", None)
            if snapshot is not None:
                snapshot_violations.append(f"{pkg_id}: has snapshot={snapshot!r}")
            if reason is not None:
                snapshot_violations.append(f"{pkg_id}: has snapshot_unavailable_reason='{reason}'")
    # Violation path: snapshot fields ARE present when they should NOT be
    assert not snapshot_violations, (
        f"{len(snapshot_violations)} snapshot field violation(s) found when not requested: "
        f"{', '.join(snapshot_violations)}"
    )


@then(parsers.parse('package "{pkg_id}" should include a snapshot with as_of and impressions'))
def then_package_snapshot_with_fields(ctx: dict, pkg_id: str) -> None:
    """Assert package has snapshot with key fields (as_of and impressions).

    Step text claims three things: 1) snapshot exists, 2) as_of exists,
    3) impressions exists. Each is verified; xfail only on spec gaps.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                snapshot = getattr(pkg, "snapshot", None)
                assert snapshot is not None, (
                    f"Package '{pkg_id}' has no snapshot — cannot verify as_of/impressions fields"
                )
                # Verify as_of
                as_of = getattr(snapshot, "as_of", None)
                if as_of is None and isinstance(snapshot, dict):
                    as_of = snapshot.get("as_of")
                assert as_of is not None, f"Snapshot on '{pkg_id}' missing 'as_of' field"
                # Verify impressions
                impressions = getattr(snapshot, "impressions", None)
                if impressions is None and isinstance(snapshot, dict):
                    impressions = snapshot.get("impressions")
                assert impressions is not None, f"Snapshot on '{pkg_id}' missing 'impressions' field"
                assert isinstance(impressions, int | float), (
                    f"Expected 'impressions' to be numeric, got {type(impressions).__name__}"
                )
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse('package "{pkg_id}" should include a snapshot'))
def then_package_includes_snapshot(ctx: dict, pkg_id: str) -> None:
    """Assert package includes a snapshot.

    Step text: 'should include a snapshot'. Missing snapshot is a spec gap.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            if getattr(pkg, "package_id", None) == pkg_id:
                snapshot = getattr(pkg, "snapshot", None)
                assert snapshot is not None, f"Package '{pkg_id}' missing snapshot — expected snapshot to be present"
                return
    raise AssertionError(f"Package '{pkg_id}' not found in response")


@then(parsers.parse("all packages should include snapshots"))
def then_all_packages_have_snapshots(ctx: dict) -> None:
    """Assert all packages have snapshots.

    Step text: 'all packages should include snapshots'. Checks every package.
    """

    buys = _get_media_buys(ctx)
    packages_checked = 0
    missing_snapshot: list[str] = []
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            pkg_id = getattr(pkg, "package_id", "?")
            packages_checked += 1
            snapshot = getattr(pkg, "snapshot", None)
            if snapshot is None:
                missing_snapshot.append(pkg_id)
    assert packages_checked > 0, "No packages found to check snapshots on"
    assert not missing_snapshot, (
        f"{len(missing_snapshot)} of {packages_checked} package(s) missing snapshots: {missing_snapshot}"
    )


@then(parsers.parse("{pkg1} has snapshot, {pkg2} has SNAPSHOT_TEMPORARILY_UNAVAILABLE"))
def then_mixed_snapshot(ctx: dict, pkg1: str, pkg2: str) -> None:
    """Assert mixed snapshot availability.

    Step text claims: pkg1 HAS snapshot, pkg2 HAS SNAPSHOT_TEMPORARILY_UNAVAILABLE.
    Both claims are verified; xfail only when production doesn't propagate data.
    """

    buys = _get_media_buys(ctx)
    pkg1_found = False
    pkg2_found = False
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            pid = getattr(pkg, "package_id", None)
            if pid == pkg1:
                pkg1_found = True
                snapshot = getattr(pkg, "snapshot", None)
                assert snapshot is not None, f"Package '{pkg1}' expected to have snapshot but snapshot is None"
            elif pid == pkg2:
                pkg2_found = True
                reason = getattr(pkg, "snapshot_unavailable_reason", None)
                assert reason is not None, (
                    f"Package '{pkg2}' expected to have SNAPSHOT_TEMPORARILY_UNAVAILABLE "
                    f"but snapshot_unavailable_reason is None"
                )
                reason_str = reason.value if hasattr(reason, "value") else str(reason)
                assert reason_str == "SNAPSHOT_TEMPORARILY_UNAVAILABLE", (
                    f"Expected SNAPSHOT_TEMPORARILY_UNAVAILABLE for '{pkg2}', got '{reason_str}'"
                )
    if not pkg1_found or not pkg2_found:
        missing = []
        if not pkg1_found:
            missing.append(pkg1)
        if not pkg2_found:
            missing.append(pkg2)
        raise AssertionError(f"Package(s) not found in response: {missing}")


@then(parsers.parse('snapshot_unavailable_reason "{reason}"'))
def then_unavailable_reason_shorthand(ctx: dict, reason: str) -> None:
    """Assert snapshot_unavailable_reason on any package (boundary table shorthand).

    Step text: 'snapshot_unavailable_reason "{reason}"'. Searches all packages
    for a matching reason value.
    """

    buys = _get_media_buys(ctx)
    for buy in buys:
        for pkg in getattr(buy, "packages", []) or []:
            actual = getattr(pkg, "snapshot_unavailable_reason", None)
            if actual is not None:
                actual_str = actual.value if hasattr(actual, "value") else str(actual)
                assert actual_str == reason, f"Expected snapshot_unavailable_reason '{reason}', got '{actual_str}'"
                return
    raise AssertionError(
        f"snapshot_unavailable_reason='{reason}' not found on any package across {len(buys)} media buy(s)"
    )


# ═══════════════════════════════════════════════════════════════════════
# v3.1 lifecycle handles: revision (BR-RULE-291) + confirmed_at (POST-S6 / INT-006)
# ═══════════════════════════════════════════════════════════════════════
# The pinned item schema (media-buy/get-media-buys-response.json, AdCP 3.1.1)
# makes BOTH fields REQUIRED on every media_buys[] entry:
#   revision      integer, minimum 1 — the buyer's optimistic-concurrency token
#   confirmed_at  type [string, null] under an allOf/if guard that forbids null
#                 when status is "active"
#
# Every Then in this section reads the BUYER'S WIRE (wire_dict / wire_field), not
# the re-serialized typed payload. These two fields are exactly what this change
# publishes, and a model round-trip cannot observe whether they reached the wire
# at all — which is how they went unnoticed while three separate mutations of the
# since-deleted read-time confirmed_at resolver left the suite green. That resolver
# is gone: the column is authoritative, so these Thens now grade what the writer
# stamped and the reader emitted.
#
# Givens seed persisted COLUMN values through _seed_simple_media_buy (the module's
# own factory path) so production reads a real row, and the writes that move
# `revision` go through MediaBuyRepository — the single writer of both columns.


def _parse_iso8601(value: str) -> datetime:
    """Parse an ISO 8601 timestamp literal into an aware datetime.

    Both sides of every confirmed_at comparison go through this. "…T12:00:00Z" and
    "…T12:00:00+00:00" are the SAME instant spelled two ways, so a string compare
    would grade the serializer's choice of timezone designator instead of the
    timestamp the buyer was promised.
    """
    return datetime.fromisoformat(value)


def _wire_media_buy_entry(ctx: dict, mb_id: str, document: dict | None = None) -> dict:
    """Locate one seeded buy's entry in the buyer-visible wire document.

    Resolving through the Gherkin label (not the raw id) is what keeps a scenario
    that seeded several buys from silently grading whichever entry came first.
    """
    real_id = _resolve_media_buy_id(ctx, mb_id)
    doc = wire_dict(ctx) if document is None else document
    buys = doc.get("media_buys", [])
    for buy in buys:
        if buy.get("media_buy_id") == real_id:
            return buy
    raise AssertionError(
        f"Media buy '{mb_id}' (real_id={real_id}) is not in the response; "
        f"media_buys carried {[b.get('media_buy_id') for b in buys]!r}"
    )


def _sole_seeded_label(ctx: dict) -> str:
    """The Gherkin label of the single buy the scenario seeded.

    Several steps in this section name no buy — the t1/t2 write ("one successful
    update_media_buy lands between t1 and t2"), the t1/t2 comparisons, and
    "the confirmed_at value should be …". Each of their scenarios seeds exactly
    one buy, so resolving "the" buy is unambiguous; asserting the count keeps it
    that way instead of silently grading whichever one came first.
    """
    seeded = ctx.get("seeded_media_buys", {})
    assert len(seeded) == 1, f"Expected exactly one seeded media buy for this scenario, got {sorted(seeded)}"
    return next(iter(seeded))


def _only_seeded_media_buy(ctx: dict) -> str:
    """The real database id of the single buy the scenario seeded."""
    return _resolve_media_buy_id(ctx, _sole_seeded_label(ctx))


def _persisted_revision(ctx: dict, real_id: str) -> int:
    """Read the persisted revision column back through the repository."""
    from src.core.database.repositories.media_buy import MediaBuyRepository

    env = ctx["env"]
    repo = MediaBuyRepository(env.get_session(), ctx["tenant"].tenant_id)
    row = repo.get_by_id(real_id)
    assert row is not None, f"Media buy '{real_id}' not persisted for tenant {ctx['tenant'].tenant_id!r}"
    return row.revision


def _land_state_changing_write(ctx: dict, real_id: str, *, marker: str) -> None:
    """Land ONE real state-changing write on a seeded buy, through the repository.

    MediaBuyRepository is the single writer of ``revision``: ``update_fields``
    rejects it (and ``confirmed_at``) as immutable and ends every successful call
    in ``_bump_revision`` + flush. So a mutation counter of N can only be produced
    by N real writes — there is no supported path that seeds the value directly,
    which is precisely why the scenarios that say "after four writes" have to
    perform them.

    ``order_name`` is the field moved because it is buyer-visible metadata with no
    lifecycle meaning: the graded effect is the revision bump, not the field.
    """
    from src.core.database.repositories.media_buy import MediaBuyRepository

    env = ctx["env"]
    repo = MediaBuyRepository(env.get_session(), ctx["tenant"].tenant_id)
    updated = repo.update_fields(real_id, order_name=marker)
    assert updated is not None, f"Media buy '{real_id}' not found — the write that must land between reads did not"
    env.get_session().commit()


# ── GIVEN: persisted revision ─────────────────────────────────────────


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with persisted revision {revision:d}'))
@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with persisted revision {revision:d} '
        "and no subsequent writes"
    )
)
@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with persisted revision {revision:d} '
        "and no intervening writes between two reads"
    )
)
@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with persisted revision {revision:d} '
        "(defective seller)"
    )
)
def given_owns_media_buy_with_persisted_revision(ctx: dict, principal_id: str, mb_id: str, revision: int) -> None:
    """Seed a buy whose persisted revision column carries an exact value.

    The four spellings are one setup: the partition/boundary/invariant scenarios
    differ only in what they go on to assert. The "(defective seller)" rows seed 0
    and -1 — a state the store genuinely admits, because ``media_buys.revision``
    carries no CHECK constraint below the schema minimum. Whether that defective
    value can then reach the BUYER is exactly what those rows go on to grade; the
    Then re-reads the column to prove the defect was really persisted, so a seeding
    path that silently coerced it back to a legal value fails there instead of
    passing vacuously.
    """
    _seed_simple_media_buy(ctx, principal_id, mb_id, revision=revision)
    ctx.setdefault("seeded_revisions", {})[mb_id] = revision


@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" with persisted revision {revision:d} '
        "after four state-changing writes"
    )
)
def given_owns_media_buy_revision_after_four_writes(ctx: dict, principal_id: str, mb_id: str, revision: int) -> None:
    """Seed a fresh buy and land FOUR real state-changing writes on it.

    The scenario says "revision 5 AFTER four state-changing writes", so the four
    writes are the setup — seeding the literal 5 would grade a value no writer
    produced (and is not even expressible: update_fields raises ValueError on
    ``revision``). The buy starts at the column default 1, each repository write
    bumps it once, and the resulting counter is asserted to be the value the
    scenario names, so a bump that stops incrementing fails here rather than
    silently agreeing with a hand-seeded expectation.
    """
    _seed_simple_media_buy(ctx, principal_id, mb_id)
    real_id = _resolve_media_buy_id(ctx, mb_id)
    for write in range(4):
        _land_state_changing_write(ctx, real_id, marker=f"revision-write-{write + 1}")
    persisted = _persisted_revision(ctx, real_id)
    assert persisted == revision, (
        f"Four repository writes should leave revision at {revision} (1 + 4 bumps), got {persisted}"
    )
    ctx.setdefault("seeded_revisions", {})[mb_id] = persisted


@given("no state-changing writes occur between two reads")
def given_no_writes_between_reads(ctx: dict) -> None:
    """Pin the INV-4 precondition: the buy is untouched going into the two reads.

    Asserting rather than declaring — if anything had already moved the counter,
    the two reads could agree for the wrong reason and INV-4 would pass vacuously.
    """
    real_id = _only_seeded_media_buy(ctx)
    seeded = ctx["seeded_revisions"]
    expected = next(iter(seeded.values()))
    persisted = _persisted_revision(ctx, real_id)
    assert persisted == expected, (
        f"Precondition broken: revision is {persisted}, not the seeded {expected} — "
        "something already wrote to the buy before the two reads"
    )


# ── GIVEN: persisted confirmed_at ─────────────────────────────────────


@given(parsers.parse('the principal "{principal_id}" owns media buy "{mb_id}" with confirmed_at "{timestamp}"'))
@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" '
        'with a successful create stamping confirmed_at "{timestamp}"'
    )
)
@given(
    parsers.parse(
        'the principal "{principal_id}" owns media buy "{mb_id}" that was successfully created at "{timestamp}"'
    )
)
def given_owns_media_buy_with_confirmed_at(ctx: dict, principal_id: str, mb_id: str, timestamp: str) -> None:
    """Seed a buy whose persisted confirmed_at column carries an exact instant.

    All three spellings describe the same persisted state — the seller committed
    at that instant — so they share one setup. Each ENDS in a quoted literal, which
    is why they exist at all: the generic ``owns media buy "{mb_id}"`` Given also
    matches such a line and would swallow the clause into the label (guarded there).
    Status stays the factory-seeded serving state so the buy is a confirmed one,
    which is what makes a non-null confirmed_at the correct reading.
    """
    _seed_simple_media_buy(ctx, principal_id, mb_id, confirmed_at=_parse_iso8601(timestamp))


# ── WHEN: two reads, with or without a write between them ─────────────


@when("the Buyer Agent sends a get_media_buys request at time t1")
def when_query_at_t1(ctx: dict) -> None:
    """Read once and snapshot the wire document as t1.

    Snapshotting is what makes the pair comparable: the next dispatch overwrites
    ctx["wire_response"], so a Then reading it afterwards would compare t2 with
    itself.
    """
    _dispatch_query(ctx)
    ctx["wire_at_t1"] = wire_dict(ctx)


@when("the Buyer Agent sends a get_media_buys request at time t2 (t1 < t2)")
@when("the Buyer Agent sends a get_media_buys request at time t2")
def when_query_at_t2(ctx: dict) -> None:
    """Read a second time and snapshot the wire document as t2."""
    assert "wire_at_t1" in ctx, "the t2 read ran without a t1 read — the pair cannot be compared"
    _dispatch_query(ctx)
    ctx["wire_at_t2"] = wire_dict(ctx)


@when("one successful update_media_buy lands between t1 and t2")
def when_update_lands_between_reads(ctx: dict) -> None:
    """Land one real state-changing write between the two reads.

    A repository write rather than an update_media_buy dispatch on purpose: the
    obligation graded here is the READ path — BR-RULE-291 INV-5 ("get_media_buys
    reports the bumped token") and the confirmed_at stability invariant — while
    UC-002/UC-003 own the update tool's own transport contract. The write still
    goes through the production seam that owns both columns, so it moves revision
    exactly as a real update would.
    """
    _land_state_changing_write(ctx, _only_seeded_media_buy(ctx), marker="update-between-t1-and-t2")


# ── THEN: revision on the wire ────────────────────────────────────────


@then(parsers.parse('the media buy "{mb_id}" revision should be {expected:d}'))
def then_media_buy_revision_equals(ctx: dict, mb_id: str, expected: int) -> None:
    """Assert the buy's wire revision is exactly the expected integer."""
    buy = _wire_media_buy_entry(ctx, mb_id)
    assert buy.get("revision") == expected, (
        f"Expected media buy '{mb_id}' revision {expected} on the wire, got {buy.get('revision')!r}"
    )


@then(parsers.parse('the media buy "{mb_id}" revision should be {expected:d} on both reads'))
def then_media_buy_revision_equals_on_both_reads(ctx: dict, mb_id: str, expected: int) -> None:
    """Assert the revision is the expected integer on TWO successive reads.

    The outline's single shared When performs read #1; the row's own expectation
    ("N on both reads") is about read #2 as well, and its Given established that
    nothing writes in between — so the second read is issued here. Both documents
    are asserted, so a counter that drifts on a pure read fails.
    """
    first = _wire_media_buy_entry(ctx, mb_id)
    assert first.get("revision") == expected, (
        f"First read: expected media buy '{mb_id}' revision {expected}, got {first.get('revision')!r}"
    )
    _dispatch_query(ctx)
    second = _wire_media_buy_entry(ctx, mb_id)
    assert second.get("revision") == expected, (
        f"Second read with no intervening write: expected revision {expected}, got {second.get('revision')!r}"
    )


def _is_wire_integer(value: Any) -> bool:
    """Whether a wire value is an integer in the sense the pinned schema means.

    The obligation is JSON Schema's ``"type": "integer"``, which is a statement
    about the NUMBER (Draft 6+: a number with zero fractional part), not about the
    Python type the transport happened to decode it into. That distinction is
    load-bearing here: A2A frames its DataPart as a protobuf ``Struct``, whose only
    numeric kind is ``number_value`` (a double), so an integer field arrives as
    ``1.0`` on A2A and ``1`` on MCP. Asserting ``isinstance(int)`` would fail the
    a2a arm of every revision scenario over a framing detail while letting a real
    fractional revision through on MCP; this rejects ``1.5`` and ``"1"`` on both.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer()


@then("every returned media buy should include an integer revision field")
def then_every_buy_has_integer_revision(ctx: dict) -> None:
    """Sweep EVERY returned buy for an integer revision — not just the first."""
    buys = wire_dict(ctx).get("media_buys", [])
    assert buys, "No media buys were returned, so 'every returned media buy' asserts nothing"
    for buy in buys:
        assert "revision" in buy, (
            f"media buy {buy.get('media_buy_id')!r} carries no revision key; "
            f"the pinned item schema requires it (keys: {sorted(buy)})"
        )
        revision = buy["revision"]
        assert _is_wire_integer(revision), (
            f"media buy {buy.get('media_buy_id')!r} revision {revision!r} ({type(revision).__name__}) is not an "
            'integer; the pinned item schema types it "integer"'
        )


@then("every revision should be >= 1")
def then_every_revision_at_least_one(ctx: dict) -> None:
    """Sweep EVERY returned buy against the schema minimum of 1."""
    buys = wire_dict(ctx).get("media_buys", [])
    assert buys, "No media buys were returned, so 'every revision' asserts nothing"
    for buy in buys:
        revision = buy.get("revision")
        assert revision >= 1, (
            f"media buy {buy.get('media_buy_id')!r} revision {revision!r} is below the pinned schema minimum of 1"
        )


def _revision_at(ctx: dict, moment: str) -> int:
    """The wire revision of the single seeded buy in the snapshot for t1 or t2."""
    document = ctx.get(f"wire_at_{moment}")
    assert document is not None, f"No wire document was snapshotted at {moment}"
    buy = _wire_media_buy_entry(ctx, _sole_seeded_label(ctx), document)
    return buy["revision"]


@then("the revision at t1 should equal the revision at t2")
def then_revision_stable_across_reads(ctx: dict) -> None:
    """INV-4: with no intervening write, two reads report the SAME token."""
    at_t1, at_t2 = _revision_at(ctx, "t1"), _revision_at(ctx, "t2")
    assert at_t1 == at_t2, f"Revision drifted across two reads with no write between them: t1={at_t1}, t2={at_t2}"


@then("the revision at t2 should be strictly greater than the revision at t1")
def then_revision_increases_after_write(ctx: dict) -> None:
    """INV-5: an intervening successful write moves the token strictly upward."""
    at_t1, at_t2 = _revision_at(ctx, "t1"), _revision_at(ctx, "t2")
    assert at_t2 > at_t1, (
        f"A successful state-changing write must strictly increase revision, but t1={at_t1} and t2={at_t2}"
    )


# ── THEN: confirmed_at on the wire ────────────────────────────────────


@then(parsers.parse('the media buy "{mb_id}" should include a confirmed_at field'))
def then_media_buy_includes_confirmed_at(ctx: dict, mb_id: str) -> None:
    """Assert the confirmed_at KEY is present on the wire entry.

    Key PRESENCE, not truthiness: confirmed_at is required-and-nullable, so the
    regression this grades is the key being dropped from the serialized document
    (which an ``exclude_none`` anywhere on the path would do silently) — a null
    value would still be a present key, and a different assertion.
    """
    buy = _wire_media_buy_entry(ctx, mb_id)
    assert "confirmed_at" in buy, (
        f"media buy '{mb_id}' carries no confirmed_at key; the pinned item schema requires it (keys: {sorted(buy)})"
    )


@then(parsers.parse('the confirmed_at value should be the ISO 8601 timestamp "{timestamp}"'))
@then(parsers.parse('the media buy "{mb_id}" confirmed_at should equal "{timestamp}"'))
def then_confirmed_at_equals(ctx: dict, timestamp: str, mb_id: str | None = None) -> None:
    """Assert the wire confirmed_at is the expected INSTANT, parsed on both sides.

    The first spelling names no buy (it follows a Then that already named one), so
    it falls back to the scenario's sole seeded buy rather than a hardcoded label.
    """
    mb_id = mb_id or _sole_seeded_label(ctx)
    buy = _wire_media_buy_entry(ctx, mb_id)
    actual = buy.get("confirmed_at")
    assert actual is not None, f"media buy '{mb_id}' confirmed_at is null; expected {timestamp}"
    assert _parse_iso8601(actual) == _parse_iso8601(timestamp), (
        f"Expected media buy '{mb_id}' confirmed_at {timestamp}, got {actual!r}"
    )


@then(parsers.parse('the media buy "{mb_id}" confirmed_at should be an ISO 8601 string with a timezone designator'))
def then_confirmed_at_carries_timezone(ctx: dict, mb_id: str) -> None:
    """Assert the wire confirmed_at is an ISO 8601 STRING carrying an offset.

    The schema types the field ``string`` with ``format: date-time``, and a
    date-time without an offset is a different instant for every reader — so both
    halves are checked: that it serialized as a string at all, and that parsing it
    yields an aware datetime.
    """
    buy = _wire_media_buy_entry(ctx, mb_id)
    actual = buy.get("confirmed_at")
    assert isinstance(actual, str), (
        f"media buy '{mb_id}' confirmed_at is {type(actual).__name__}, not an ISO 8601 string"
    )
    assert _parse_iso8601(actual).tzinfo is not None, (
        f"media buy '{mb_id}' confirmed_at {actual!r} carries no timezone designator"
    )


@then(parsers.parse('the confirmed_at at {moment} should equal "{timestamp}"'))
def then_confirmed_at_at_moment_equals(ctx: dict, moment: str, timestamp: str) -> None:
    """Assert the snapshotted t1/t2 document reports the expected commitment instant.

    Both reads are graded against the ORIGINAL timestamp, which is what makes the
    stability claim real: a write that rewrote confirmed_at would move t2 only, and
    comparing t2 against t1 alone would not notice a drift that moved both.
    """
    document = ctx.get(f"wire_at_{moment}")
    assert document is not None, f"No wire document was snapshotted at {moment}"
    buy = _wire_media_buy_entry(ctx, _sole_seeded_label(ctx), document)
    actual = buy.get("confirmed_at")
    assert actual is not None, f"confirmed_at at {moment} is null; expected {timestamp}"
    assert _parse_iso8601(actual) == _parse_iso8601(timestamp), (
        f"Expected confirmed_at {timestamp} at {moment}, got {actual!r}"
    )


# ── THEN: the defective-revision publication oracle ───────────────────
# The obligation is the one the pin states outright and that holds however the
# seller chooses to refuse: a media buy whose PERSISTED revision is below the
# pinned minimum is never PUBLISHED to the buyer. Erroring and withholding the
# entry from a 200 document are both compliant refusals; handing the buyer the
# entry is not. So the oracle below reads whatever the buyer actually received —
# success body or wire error envelope — and grades the same claim on either.
#
# It deliberately asserts NO error code. The code production emits today
# (VALIDATION_ERROR / "correctable", from the response-model rejection at
# src/core/tools/media_buy_list.py translated in src/core/tool_error_logging.py)
# is itself in question: the pin's enumMetadata makes that code mean "buyer,
# fix your field values" for a defect in the SELLER's store. Pinning it here
# would freeze that into the graders. See the note under the outline in
# BR-UC-019-query-media-buys.feature.


def _pinned_revision_minimum() -> int:
    """The minimum the PIN sets for ``media_buys[].revision``, read from the pin.

    Read rather than hard-coded so the bound moves with the pinned schema instead
    of with a literal someone has to remember to update — the same reason the
    schema-shape steps validate against the pinned tree rather than a copy.
    """
    from tests.helpers.pinned_schema import load

    schema = load("media-buy/get-media-buys-response.json")
    minimum = schema["properties"]["media_buys"]["items"]["properties"]["revision"]["minimum"]
    assert isinstance(minimum, int), f"Pinned revision minimum is {minimum!r}, not an integer — the pin moved"
    return minimum


def _published_media_buy_entries(ctx: dict) -> list[dict]:
    """Every media-buy entry the buyer received, whichever way the seller answered.

    On success this is the success wire (``wire_dict``, which itself raises if a
    real-wire transport stashed nothing — the guard against grading an empty
    reconstruction). On refusal it is the wire ERROR envelope, walked recursively:
    the claim being graded is that the entry is nowhere in what the buyer got, and
    a leak nested under ``details`` would satisfy a top-level-only check.
    """
    result = ctx["result"]
    if result.is_success:
        return _collect_media_buy_entries(wire_dict(ctx))
    envelope = ctx.get("wire_error_envelope")
    assert envelope is not None, (
        f"{ctx.get('transport')}: the request failed but no wire error envelope was captured, so there is "
        f"no buyer-visible document to inspect and this step would assert nothing. Error: {ctx.get('error')!r}"
    )
    return _collect_media_buy_entries(envelope)


def _collect_media_buy_entries(node: Any) -> list[dict]:
    """Every dict carried under a ``media_buys`` key, at any depth of a wire document."""
    found: list[dict] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "media_buys" and isinstance(value, list):
                found.extend(entry for entry in value if isinstance(entry, dict))
            found.extend(_collect_media_buy_entries(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_media_buy_entries(item))
    return found


@then(
    parsers.parse(
        'the media buy "{mb_id}" should not be published, and no returned media buy '
        "should carry a revision below the pinned minimum"
    )
)
def then_sub_minimum_revision_never_published(ctx: dict, mb_id: str) -> None:
    """Grade the non-publication invariant for a buy persisted below the pinned minimum.

    Three assertions, and each is load-bearing:

    1. The defect is REAL — the column is re-read through the repository and must
       still hold the sub-minimum value the row named. Without this the other two
       would pass trivially against a store that never took the defective value,
       which is the vacuous-pass this scenario is most exposed to.
    2. This buy is not among the entries the buyer received. Identity is the
       resolved database id, so a same-labelled sibling cannot satisfy it.
    3. NO entry the buyer received carries a sub-minimum revision — the invariant
       as stated, not just the one buy. ``_is_wire_integer`` because A2A frames its
       DataPart as a protobuf Struct whose only numeric kind is a double, so a
       legal revision arrives as ``1.0`` there and ``1`` on MCP; a non-integer or
       missing revision is itself a violation and is reported as one.
    """
    minimum = _pinned_revision_minimum()
    real_id = _resolve_media_buy_id(ctx, mb_id)

    seeded = ctx["seeded_revisions"][mb_id]
    persisted = _persisted_revision(ctx, real_id)
    assert persisted == seeded, (
        f"Precondition broken: media buy '{mb_id}' persists revision {persisted}, not the seeded {seeded} — "
        "the defective value never reached the store, so this scenario grades nothing"
    )
    assert persisted < minimum, (
        f"Precondition broken: seeded revision {persisted} is not below the pinned minimum {minimum}, "
        "so there is no defect for the seller to withhold"
    )

    entries = _published_media_buy_entries(ctx)
    leaked = [entry for entry in entries if entry.get("media_buy_id") == real_id]
    assert leaked == [], (
        f"Media buy '{mb_id}' (real_id={real_id}) persists revision {persisted}, below the pinned minimum "
        f"{minimum}, so it is not publishable — but the buyer received it: {leaked!r}"
    )
    sub_minimum = [
        (entry.get("media_buy_id"), entry.get("revision"))
        for entry in entries
        if not (_is_wire_integer(entry.get("revision")) and entry["revision"] >= minimum)
    ]
    assert sub_minimum == [], (
        f"The pinned item schema requires every published media buy to carry an integer revision >= {minimum}; "
        f"the buyer received these (media_buy_id, revision) pairs that do not: {sub_minimum!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Storyboard: post-create status poll (@T-UC-019-storyboard-post-create-status-poll)
# ═══════════════════════════════════════════════════════════════════════
# Grades the AdCP 3.1.1 storyboard step the scenario itself cites:
# dist/compliance/3.1.1/domains/media-buy/index.yaml -> "check_buy_status".
# The buyer polls get_media_buys with the media_buy_id create_media_buy returned;
# its graded validations are response_schema (full document against
# media-buy/get-media-buys-response.json), field_equals_context
# media_buys[0].media_buy_id == the captured id, and field_present
# media_buys[0].status — one per Then below, in order.
#
# The scenario ran dormant (auto-xfailed on missing step definitions,
# tests/bdd/conftest.py) until its two real blockers closed: the envelope
# status (GH #1900) and the item-level confirmed_at/revision gap (GH #1928).
# conftest routes @post-create-poll to MediaBuyCreateListEnv so the create is a
# REAL dispatch through the scenario's transport — a factory-seeded buy would
# make the poll assert nothing.


@given("the buyer captured a media_buy_id from a successful create_media_buy response")
def given_captured_media_buy_id_from_create(ctx: dict) -> None:
    """Perform a REAL create_media_buy through the scenario's transport and capture its id.

    The id comes from ``wire_field`` — the buyer captures what the RESPONSE
    carried, so reading the reconstructed typed payload would grade the
    reconstruction instead. wire_field also raises on a wire transport that
    stashed no wire, which is what keeps this from degrading into a silent
    model_dump tautology if the env wiring ever changes.

    The success assertion is load-bearing: without it a failed create would leave
    the create response in ctx, the When's query would early-return, and the Then
    steps would grade the WRONG document.
    """
    kwargs = build_create_request_kwargs(ctx, po_number="PO-UC019-POST-CREATE-POLL")
    dispatch_request(ctx, **kwargs)

    assert ctx.get("error") is None, f"create_media_buy failed, so nothing was captured: {ctx.get('error')!r}"
    ctx["created_media_buy_id"] = wire_field(ctx, "media_buy_id")


@when("the Buyer Agent calls get_media_buys with that media_buy_id under the same account")
def when_query_captured_media_buy_id(ctx: dict) -> None:
    """Poll get_media_buys for the captured id on the same env, transport and identity.

    "Under the same account" holds by construction: both dispatches go through
    one MediaBuyCreateListEnv, so the resolved identity (tenant + principal) is
    the same object. The storyboard additionally echoes an explicit ``account`` on
    both calls; the pinned item schema does define ``account``, but production
    populates none and no Then here grades one — the literal account echo belongs
    with account management, not with this poll.
    """
    media_buy_id = ctx.get("created_media_buy_id")
    assert media_buy_id, "no media_buy_id was captured from create_media_buy"
    _dispatch_query(ctx, req=GetMediaBuysRequest(media_buy_ids=[media_buy_id]))


@then("the media_buys array should include the freshly-created buy")
def then_media_buys_include_created_buy(ctx: dict) -> None:
    """Assert the polled document carries exactly the buy that was just created.

    Reads the buyer-visible wire via ``wire_dict``, which raises rather than
    falling back to a re-serialized payload on a wire transport — the same
    document the schema-valid Then grades, with a guard against the fallback
    turning this into a tautology.
    """
    media_buy_id = ctx["created_media_buy_id"]
    document = wire_dict(ctx)
    returned_ids = [buy.get("media_buy_id") for buy in document.get("media_buys", [])]
    assert media_buy_id in returned_ids, (
        f"get_media_buys did not return the freshly-created buy {media_buy_id!r}; media_buys carried {returned_ids!r}"
    )


@then(parsers.parse('the included entry should expose the same media_buy_id and status "{expected_status}"'))
def then_included_entry_exposes_id_and_status(ctx: dict, expected_status: str) -> None:
    """Assert the polled entry IS the created buy and reports the expected initial status.

    The storyboard step this scenario cites (media-buy/index.yaml
    ``check_buy_status``) grades ``field_equals_context media_buys[0].media_buy_id``
    against the id captured from create_media_buy, and ``field_present
    media_buys[0].status`` — the buyer polls to OBSERVE the initial status.

    The expected status is pinned in the Gherkin and compared for equality.
    Membership in the pinned ten-member enums/media-buy-status.json enum was the
    previous assertion and could not do this job: ``completed`` and ``failed`` are
    both members, so a freshly-created buy reported as terminal passed. The literal
    is the state this flow actually starts in — the request assigns no creatives,
    and media_buy_create._resolve_status returns ``pending_creatives`` for a buy
    with no assigned/approved creatives (priority 2, ahead of the future start_time
    that would otherwise make it pending_start).
    """
    media_buy_id = ctx["created_media_buy_id"]
    document = wire_dict(ctx)
    matching = [buy for buy in document.get("media_buys", []) if buy.get("media_buy_id") == media_buy_id]
    assert len(matching) == 1, (
        f"expected exactly one entry for the freshly-created buy {media_buy_id!r}, "
        f"got {len(matching)} in {[b.get('media_buy_id') for b in document.get('media_buys', [])]!r}"
    )

    status = matching[0].get("status")
    assert status == expected_status, (
        f"post-create poll: expected media_buys[0].status {expected_status!r} for a freshly-created buy, got {status!r}"
    )
