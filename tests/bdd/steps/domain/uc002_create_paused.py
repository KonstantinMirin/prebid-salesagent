"""Step definitions for the locally-added UC-002 create-in-paused-state feature.

Grades the create half of the AdCP 3.1.1 `paused` request field (GH #1619): the
buyer's intent must survive every transport boundary, be reported on the packages
the seller books, and be persisted on the buy so the read-surface precedence rule
(local-uc019-paused-status-precedence.feature) has something to consume.

See features/local-uc002-create-paused.feature for the schema citation.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then

from src.core.database.repositories.media_buy import MediaBuyRepository
from tests.bdd.steps._outcome_helpers import wire_dict


def _as_bool(flag: str) -> bool:
    """Parse a Gherkin true/false literal, failing loudly on anything else.

    A silent ``== "true"`` coercion would turn a typo ("ture") into a passing
    false-expectation, so unknown literals raise instead.
    """
    normalized = flag.strip().lower()
    if normalized not in ("true", "false"):
        raise ValueError(f"Expected 'true' or 'false' in step text, got {flag!r}")
    return normalized == "true"


@given(parsers.parse("the create request sets paused {flag}"))
def given_create_request_sets_paused(ctx: dict, flag: str) -> None:
    """Put the AdCP 3.1.1 ``paused`` field on the outgoing create request."""
    from tests.bdd.steps.generic.given_media_buy import _ensure_request_defaults

    _ensure_request_defaults(ctx)["paused"] = _as_bool(flag)


@then(parsers.parse("every package in the create response reports paused {flag}"))
def then_response_packages_report_paused(ctx: dict, flag: str) -> None:
    """Assert the REAL wire packages carry the requested paused state.

    Reads ``ctx['wire_response']`` (the buyer-facing body) rather than the
    reconstructed payload: package-level ``paused`` is what tells the buyer
    whether the seller booked delivery-suppressed line items.
    """
    expected = _as_bool(flag)
    wire = wire_dict(ctx)
    packages = wire.get("packages")
    assert packages, f"Expected packages on the create wire response, got keys: {sorted(wire)}"
    actual = [pkg.get("paused") for pkg in packages]
    assert actual == [expected] * len(packages), (
        f"Expected every package to report paused={expected}, got {actual!r} "
        f"(request paused={ctx.get('request_kwargs', {}).get('paused')!r})"
    )


def _created_media_buy(ctx: dict):
    """Return the ORM row for the buy this scenario created.

    Prefers the ``media_buy_id`` the buyer got on the wire. The manual-approval
    path returns a submitted envelope with no id, so it falls back to the single
    buy owned by the scenario's principal — unambiguous because each scenario
    runs against a freshly seeded tenant.
    """
    env = ctx["env"]
    tenant = ctx.get("tenant")
    principal = ctx.get("principal")
    assert tenant is not None, "No tenant in ctx — cannot scope the media-buy lookup"
    assert principal is not None, "No principal in ctx — cannot scope the media-buy lookup"

    # The buy was committed by the production UoW on another session; drop any
    # identity-map copy so this read reflects what production actually wrote.
    env._session.expire_all()
    repo = MediaBuyRepository(env._session, tenant.tenant_id)

    media_buy_id = wire_dict(ctx).get("media_buy_id")
    if media_buy_id:
        row = repo.get_by_id(media_buy_id)
        assert row is not None, f"Media buy '{media_buy_id}' not found for tenant '{tenant.tenant_id}'"
        return row

    rows = repo.get_by_principal(principal.principal_id)
    assert len(rows) == 1, (
        f"Expected exactly one media buy for principal '{principal.principal_id}' "
        f"(the one this scenario created), found {[r.media_buy_id for r in rows]}"
    )
    return rows[0]


@then(parsers.parse("the persisted media buy has is_paused {flag}"))
def then_persisted_media_buy_is_paused(ctx: dict, flag: str) -> None:
    """Assert the booked buy carries the paused delivery flag in the database.

    This is the hop the read surface consumes: ``resolve_canonical_status``
    reports "paused" only for a buy whose ``is_paused`` column is set, so a
    request-level flag that never reaches the column is a silent no-op.
    """
    expected = _as_bool(flag)
    row = _created_media_buy(ctx)
    assert row.is_paused is expected, (
        f"Expected persisted is_paused={expected} for '{row.media_buy_id}', got {row.is_paused!r} "
        f"(request paused={ctx.get('request_kwargs', {}).get('paused')!r})"
    )


@then(parsers.parse("every persisted package carries paused {flag}"))
def then_persisted_packages_paused(ctx: dict, flag: str) -> None:
    """Assert the stored package rows carry the requested paused state.

    The manual-approval path builds its packages in-process (no adapter response
    to inherit from) and the buyer never sees them on the submitted envelope, so
    the DB rows are the only place that hop is observable.
    """
    expected = _as_bool(flag)
    env = ctx["env"]
    tenant = ctx.get("tenant")
    row = _created_media_buy(ctx)
    packages = MediaBuyRepository(env._session, tenant.tenant_id).get_packages(row.media_buy_id)
    assert packages, f"No persisted packages for media buy '{row.media_buy_id}'"
    actual = [pkg.package_config.get("paused") for pkg in packages]
    assert actual == [expected] * len(packages), (
        f"Expected every persisted package to carry paused={expected}, got {actual!r} "
        f"(request paused={ctx.get('request_kwargs', {}).get('paused')!r})"
    )
