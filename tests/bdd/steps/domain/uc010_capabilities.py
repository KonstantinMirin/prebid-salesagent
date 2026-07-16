"""UC-010 step definitions: get_adcp_capabilities discovery (batch 1).

Batch 1 covers the envelope + account families (#1592 / salesagent-4sn7):
main flow, auth policy, no-tenant minimal, account.* outlines, protocols
filter, context echo, and version negotiation. Batches 2-3 (media_buy
families, long tail) land behind the conftest wired-tags gate.

Wire-assert philosophy (tests/CLAUDE.md § wire_response): Then steps grade
the SERIALIZED wire (``ctx["wire_response"]``) via dotted-path resolution,
not the coerced typed payload. Absent means the key is NOT on the wire —
a JSON null would be schema-invalid for these optional-object fields and
is deliberately not treated as absent.

Givens describing tenant-config surface production does not have yet record
intent in ``ctx["capabilities_config"]``; those scenarios xfail at the Then
— the correct red for the S1/S2/S3 slices (do NOT invent config columns here).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.generic._dispatch import dispatch_request

_MISSING = object()

#: 3.1.1 billing-party enum (dist/schemas/3.1.1/enums/billing-party.json).
BILLING_PARTY_ENUM = {"operator", "agent", "advertiser"}

# ── Wire helpers ─────────────────────────────────────────────────────


def _wire(ctx: dict) -> dict:
    """The serialized success-path wire the buyer receives.

    Prefers the real captured wire (REST body / MCP structured_content /
    A2A artifact). Falls back to serializing the typed payload — exercises
    the production serializer, not transport framing (IMPL-only caveat).
    """
    if ctx.get("error") is not None and ctx.get("response") is None:
        raise AssertionError(f"expected a success response, got error: {ctx['error']!r}")
    wire = ctx.get("wire_response")
    if isinstance(wire, dict):
        return wire
    return ctx["response"].model_dump(mode="json")


def _at(doc: dict, path: str) -> Any:
    """Resolve a dotted path against the wire dict; _MISSING when any hop is absent."""
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _require(ctx: dict, path: str) -> Any:
    """Resolve *path* on the wire, failing when absent OR null.

    A JSON null never satisfies presence: these are optional object/array
    fields whose schemas do not admit null — a null on the wire is a
    serialization defect, not a populated section (observed on MCP
    structured_content, which serializes None fields; #1592).
    """
    doc = _wire(ctx)
    val = _at(doc, path)
    assert val is not _MISSING, f"{path!r} absent from wire response (top-level keys: {sorted(doc)})"
    assert val is not None, f"{path!r} is JSON null on the wire — schema-invalid serialization of an unset field"
    return val


def _assert_absent(ctx: dict, path: str) -> None:
    val = _at(_wire(ctx), path)
    assert val is _MISSING, f"{path!r} unexpectedly present on the wire: {val!r}"


def _config(ctx: dict) -> dict:
    """Declared tenant-capability intent recorded by Given steps."""
    return ctx.setdefault("capabilities_config", {})


def _error_details(ctx: dict) -> dict:
    """details block of the wire error envelope (errors[0] preferred)."""
    envelope = ctx.get("wire_error_envelope") or ctx.get("synthesized_error_envelope")
    assert isinstance(envelope, dict), f"no wire error envelope captured (error={ctx.get('error')!r})"
    errors = envelope.get("errors") or [{}]
    details = errors[0].get("details") or envelope.get("adcp_error", {}).get("details")
    assert isinstance(details, dict), f"error envelope carries no details block: {envelope}"
    return details


def _quoted_list(text: str) -> list[str]:
    """Parse '"a", "b"' / 'display, social' step fragments into a list."""
    quoted = re.findall(r'"([^"]+)"', text)
    if quoted:
        return quoted
    return [part.strip() for part in text.split(",") if part.strip()]


# ── Givens: tenant / adapter / DB state ──────────────────────────────


@given("the tenant has full capabilities configured")
def given_full_capabilities(ctx: dict) -> None:
    """Declare the full-capability tenant. Production has no capability config
    surface yet — this records intent; value asserts xfail until S1/S3 land."""
    _config(ctx)["full"] = True


@given(parsers.parse("the tenant has an adapter with channels {channels}"))
def given_adapter_channels(ctx: dict, channels: str) -> None:
    ctx["env"].set_adapter_channels(_quoted_list(channels))


@given(parsers.parse("the tenant has registered publisher partnerships with domains {domains}"))
def given_publisher_partnerships(ctx: dict, domains: str) -> None:
    from tests.factories.core import PublisherPartnerFactory

    parsed = _quoted_list(domains)
    for domain in parsed:
        PublisherPartnerFactory(tenant=ctx["tenant"], publisher_domain=domain)
    ctx["publisher_domains"] = parsed


@given("the adapter provides targeting capabilities including geo")
def given_adapter_geo_targeting(ctx: dict) -> None:
    ctx["env"].set_targeting_capabilities(geo_countries=True, geo_regions=True, nielsen_dma=True)


@given("the system has known state before the request")
def given_state_snapshot(ctx: dict) -> None:
    ctx["state_snapshot"] = _db_state_snapshot(ctx["env"])


def _db_state_snapshot(env: Any) -> dict[str, int]:
    """Row counts of the mutable tables a capabilities call could touch."""
    from src.core.database.models import MediaBuy, Principal, PublisherPartner, Tenant

    env._commit_factory_data()
    return {model.__tablename__: len(env.query(model)) for model in (Tenant, Principal, PublisherPartner, MediaBuy)}


# ── Givens: auth state ───────────────────────────────────────────────


@given(parsers.re(r"the Buyer has (?P<token_state>no|valid|invalid) authentication$"))
def given_token_state(ctx: dict, token_state: str) -> None:
    ctx["token_state"] = token_state


@given("the Buyer has an invalid authentication token")
def given_invalid_token(ctx: dict) -> None:
    ctx["token_state"] = "invalid"


def _identity_for_token_state(ctx: dict) -> Any:
    """Map the declared token_state onto a harness identity.

    - no      → principal-less tenant identity (tenant Given holds; no credential)
    - valid   → env default (real factory token)
    - invalid → token matching no Principal row (real chain on MCP/A2A;
                in-process REST models the treat-as-absent outcome via the
                dep seam — the real header path is exercised on e2e_rest)
    """
    env = ctx["env"]
    state = ctx.get("token_state", "valid")
    if state == "no":
        return env.anonymous_identity()
    if state == "invalid":
        return env.invalid_token_identity()
    return _DEFAULT


_DEFAULT = object()


# ── Givens: account-family tenant config ─────────────────────────────


@given(parsers.parse("the tenant is configured with require_operator_auth {configured}"))
def given_require_operator_auth(ctx: dict, configured: str) -> None:
    _config(ctx)["require_operator_auth"] = configured  # true|false|omitted (intent only)


@given(parsers.parse("the tenant is configured with require_operator_auth true and OAuth support {oauth_state}"))
def given_oauth_support(ctx: dict, oauth_state: str) -> None:
    _config(ctx)["require_operator_auth"] = "true"
    match = re.search(r"enabled at (\S+)", oauth_state)
    _config(ctx)["authorization_endpoint"] = match.group(1) if match else None


@given(parsers.parse("the tenant is configured with required_for_products {configured}"))
def given_required_for_products(ctx: dict, configured: str) -> None:
    _config(ctx)["required_for_products"] = configured


@given(parsers.parse("the tenant billing policy is configured as {billing_config}"))
def given_billing_policy(ctx: dict, billing_config: str) -> None:
    """REAL config: tenants.supported_billing exists (#1521 lineage) — write it."""
    billing = _quoted_list(billing_config)
    ctx["env"].configure_tenant_field("supported_billing", billing)
    _config(ctx)["supported_billing"] = billing


@given("the tenant does not expose the get_account_financials task")
def given_no_account_financials(ctx: dict) -> None:
    _config(ctx)["account_financials"] = False


@given("a tenant is resolvable with partial account config")
def given_partial_account_config(ctx: dict) -> None:
    ctx["has_tenant"] = True
    _config(ctx)["partial_account"] = True


@given(parsers.parse("the tenant capabilities are configured as {capability_config}"))
def given_capability_config(ctx: dict, capability_config: str) -> None:
    """Outline-row config declaration (features-partitions). Records the raw
    row text; the row→assertion table in the satisfy-Then grades it."""
    _config(ctx)["row"] = capability_config


# ── Givens: version negotiation ──────────────────────────────────────


@given(parsers.parse("the seller speaks adcp release-precision versions {versions}"))
def given_seller_versions(ctx: dict, versions: str) -> None:
    _config(ctx)["supported_versions"] = _quoted_list(versions)


@given(parsers.parse('the seller\'s build_version is "{build_version}"'))
def given_seller_build_version(ctx: dict, build_version: str) -> None:
    _config(ctx)["build_version"] = build_version


# ── When cluster ─────────────────────────────────────────────────────


def _call_capabilities(ctx: dict, **kwargs: Any) -> None:
    """Single funnel for every capabilities dispatch (DRY).

    Honors ctx["identity"] = None (no-tenant Givens) and appends each
    response to ctx["response_history"] for dual-call comparisons.
    """
    if "identity" not in kwargs and "identity" in ctx:
        kwargs["identity"] = ctx["identity"]
    dispatch_request(ctx, **kwargs)
    ctx.setdefault("response_history", []).append((ctx.get("response"), ctx.get("error")))


@when("the Buyer Agent calls get_adcp_capabilities")
@when("the Buyer Agent calls get_adcp_capabilities without context")
@when("the Buyer Agent calls get_adcp_capabilities authenticated with a valid principal_id")
def when_call_capabilities(ctx: dict) -> None:
    """Plain dispatch aliases: no-context and valid-principal are the default
    call shape (the env default identity IS the valid principal)."""
    _call_capabilities(ctx)


@when(parsers.parse("the Buyer Agent calls get_adcp_capabilities with protocols filter {protocols}"))
def when_call_with_protocols(ctx: dict, protocols: str) -> None:
    _call_capabilities(ctx, protocols=json.loads(protocols))


@when(parsers.parse("the Buyer Agent calls get_adcp_capabilities with context {context}"))
def when_call_with_context(ctx: dict, context: str) -> None:
    request_context = json.loads(context)
    ctx["request_context"] = request_context
    _call_capabilities(ctx, context=request_context)


@when(parsers.parse('the Buyer Agent calls get_adcp_capabilities with adcp_version "{version}"'))
def when_call_with_adcp_version(ctx: dict, version: str) -> None:
    _call_capabilities(ctx, adcp_version=version)


@when(parsers.parse("the Buyer Agent calls get_adcp_capabilities with adcp_major_version {major:d}"))
def when_call_with_major_version(ctx: dict, major: int) -> None:
    _call_capabilities(ctx, adcp_major_version=major)


@when("the Buyer Agent calls get_adcp_capabilities without authentication")
def when_call_unauthenticated(ctx: dict) -> None:
    _call_capabilities(ctx, identity=ctx["env"].anonymous_identity())


@when(parsers.re(r"the Buyer Agent invokes get_adcp_capabilities via (?P<channel>MCP|A2A|REST)$"))
def when_invoke_via_channel(ctx: dict, channel: str) -> None:
    """Auth-outline dispatch: the <channel> column IS the transport (the
    pytest-level parametrization is redundant for this outline by design)."""
    ctx["transport"] = channel
    identity = _identity_for_token_state(ctx)
    if identity is _DEFAULT:
        _call_capabilities(ctx)
    else:
        _call_capabilities(ctx, identity=identity)


@when("the Buyer Agent calls get_adcp_capabilities via MCP with the token")
def when_call_mcp_invalid_token(ctx: dict) -> None:
    ctx["transport"] = "MCP"
    _call_capabilities(ctx, identity=ctx["env"].invalid_token_identity())


@when("the Buyer Agent sends a get_adcp_capabilities skill request via A2A with the token")
def when_call_a2a_invalid_token(ctx: dict) -> None:
    ctx["transport"] = "A2A"
    _call_capabilities(ctx, identity=ctx["env"].invalid_token_identity())


# ── Thens: adcp envelope ─────────────────────────────────────────────


@then("the response should include adcp.major_versions containing 3")
def then_major_versions(ctx: dict) -> None:
    assert 3 in _require(ctx, "adcp.major_versions")


@then("the response should include adcp.idempotency with a boolean supported discriminator")
def then_idempotency_discriminator(ctx: dict) -> None:
    idempotency = _require(ctx, "adcp.idempotency")
    assert isinstance(idempotency.get("supported"), bool), f"idempotency.supported not a boolean: {idempotency}"


@then("the response should include adcp.supported_versions as a non-empty array")
def then_supported_versions_nonempty(ctx: dict) -> None:
    versions = _require(ctx, "adcp.supported_versions")
    assert isinstance(versions, list) and versions, f"adcp.supported_versions not a non-empty array: {versions!r}"


@then(parsers.parse('each value in adcp.supported_versions should match pattern "{pattern}"'))
def then_supported_versions_pattern(ctx: dict, pattern: str) -> None:
    for value in _require(ctx, "adcp.supported_versions"):
        assert re.fullmatch(pattern, value), f"supported_versions entry {value!r} does not match {pattern!r}"


@then(parsers.parse('the response should include supported_protocols containing "{protocol}"'))
def then_supported_protocols_contains(ctx: dict, protocol: str) -> None:
    assert protocol in _require(ctx, "supported_protocols")


@then(parsers.parse('supported_protocols should contain "{protocol}"'))
def then_supported_protocols_contains_short(ctx: dict, protocol: str) -> None:
    assert protocol in _require(ctx, "supported_protocols")


@then("the response should include last_updated as a valid timestamp")
@then("the response should include last_updated as a valid ISO 8601 timestamp")
def then_last_updated_valid(ctx: dict) -> None:
    from datetime import datetime

    raw = _require(ctx, "last_updated")
    datetime.fromisoformat(str(raw).replace("Z", "+00:00"))  # raises on malformed


# ── Thens: account block ─────────────────────────────────────────────


def _assert_billing_party_array(value: Any) -> None:
    assert isinstance(value, list) and value, f"supported_billing not a non-empty array: {value!r}"
    assert set(value) <= BILLING_PARTY_ENUM, f"supported_billing carries non-enum values: {value!r}"


@then(
    "account.supported_billing should be a non-empty array of billing-party enum values matching the tenant billing config"
)
def then_supported_billing_matches_config(ctx: dict) -> None:
    value = _require(ctx, "account.supported_billing")
    _assert_billing_party_array(value)
    declared = _config(ctx).get("supported_billing")
    if declared is not None:
        assert sorted(value) == sorted(declared), f"supported_billing {value!r} != tenant config {declared!r}"


@then("account.supported_billing should be a non-empty array")
def then_supported_billing_nonempty(ctx: dict) -> None:
    value = _require(ctx, "account.supported_billing")
    assert isinstance(value, list) and value, f"supported_billing not a non-empty array: {value!r}"


@then(parsers.parse("account.supported_billing should equal {expected_set}"))
def then_supported_billing_equals(ctx: dict, expected_set: str) -> None:
    expected = [part.strip() for part in expected_set.strip("[]").split(",") if part.strip()]
    value = _require(ctx, "account.supported_billing")
    assert sorted(value) == sorted(expected), f"supported_billing {value!r} != {expected!r}"


@then('each supported_billing value should be one of "operator", "agent", "advertiser"')
def then_supported_billing_enum(ctx: dict) -> None:
    _assert_billing_party_array(_require(ctx, "account.supported_billing"))


@then("account.sandbox should equal the tenant-configured sandbox value")
def then_sandbox_matches_config(ctx: dict) -> None:
    value = _require(ctx, "account.sandbox")
    assert isinstance(value, bool), f"account.sandbox not a boolean: {value!r}"
    declared = _config(ctx).get("sandbox")
    if declared is not None:
        assert value is declared, f"account.sandbox {value!r} != tenant config {declared!r}"


def _expect_flag(ctx: dict, path: str, expected: str) -> None:
    """Grade an outline <expected> column: 'equal to true/false' | 'absent' |
    'absent or false' | 'equal to "..." as a URI'."""
    value = _at(_wire(ctx), path)
    if expected == "absent":
        assert value is _MISSING, f"{path} unexpectedly present: {value!r}"
    elif expected == "absent or false":
        assert value is _MISSING or value is False, f"{path} expected absent-or-false, got {value!r}"
    elif expected in ("equal to true", "equal to false"):
        assert value is (expected == "equal to true"), f"{path} expected {expected}, got {value!r}"
    else:
        match = re.match(r'equal to "([^"]+)"', expected)
        assert match, f"unrecognized expected column: {expected!r}"
        assert value == match.group(1), f"{path} expected {match.group(1)!r}, got {value!r}"


@then(parsers.parse("account.require_operator_auth should be {expected}"))
def then_require_operator_auth(ctx: dict, expected: str) -> None:
    _expect_flag(ctx, "account.require_operator_auth", expected)


@then(parsers.parse("account.authorization_endpoint should be {expected}"))
def then_authorization_endpoint(ctx: dict, expected: str) -> None:
    _expect_flag(ctx, "account.authorization_endpoint", expected.removesuffix(" as a URI"))


@then(parsers.parse("account.required_for_products should be {expected}"))
def then_required_for_products(ctx: dict, expected: str) -> None:
    _expect_flag(ctx, "account.required_for_products", expected)


@then("account.account_financials should be absent or false")
def then_account_financials(ctx: dict) -> None:
    _expect_flag(ctx, "account.account_financials", "absent or false")


@then("the account section should be present with a non-empty supported_billing")
def then_account_present_with_billing(ctx: dict) -> None:
    account = _require(ctx, "account")
    assert isinstance(account, dict), f"account not an object: {account!r}"
    _assert_billing_party_array(account.get("supported_billing"))


@then(
    parsers.re(
        r"the account section should be (?P<state>absent|present"
        r"|present with supported_billing only and no optional fields)$"
    )
)
def then_account_state(ctx: dict, state: str) -> None:
    if state == "absent":
        _assert_absent(ctx, "account")
        return
    account = _require(ctx, "account")
    _assert_billing_party_array(account.get("supported_billing"))
    if state.startswith("present with supported_billing only"):
        extras = set(account) - {"supported_billing"}
        assert not extras, f"degraded account block carries optional fields: {sorted(extras)}"


@then("a present account section should include supported_billing as a non-empty array of billing-party enum values")
def then_present_account_billing(ctx: dict) -> None:
    account = _at(_wire(ctx), "account")
    if account is _MISSING:
        return  # conditional Then: only grades a present block
    _assert_billing_party_array(account.get("supported_billing"))


# ── Thens: media_buy block (batch-1 subset) ──────────────────────────

_FEATURE_FLAGS = (
    "inline_creative_management",
    "property_list_filtering",
    "catalog_management",
    "committed_metrics_supported",
)


@then("media_buy.features should conform to the 4-flag media-buy-features shape with tenant-configured values")
def then_features_shape(ctx: dict) -> None:
    features = _require(ctx, "media_buy.features")
    for flag in _FEATURE_FLAGS:
        assert isinstance(features.get(flag), bool), f"features.{flag} not a boolean: {features!r}"
    declared = _config(ctx).get("features")
    if declared is not None:
        mismatches = {k: (features.get(k), v) for k, v in declared.items() if features.get(k) is not v}
        assert not mismatches, f"features differ from tenant config: {mismatches}"


@then("media_buy.supported_pricing_models should equal the exact set derived from the tenant adapter")
def then_pricing_models(ctx: dict) -> None:
    models = _require(ctx, "media_buy.supported_pricing_models")
    assert isinstance(models, list) and models, f"supported_pricing_models not a non-empty array: {models!r}"
    assert len(models) == len(set(models)), f"supported_pricing_models has duplicates: {models!r}"


@then("media_buy.reporting_delivery_methods should equal the tenant-configured delivery methods")
def then_reporting_delivery_methods(ctx: dict) -> None:
    methods = _require(ctx, "media_buy.reporting_delivery_methods")
    assert isinstance(methods, list) and methods, f"reporting_delivery_methods not a non-empty array: {methods!r}"


@then("media_buy.execution.targeting should include geo_countries and geo_regions as booleans")
def then_targeting_geo_booleans(ctx: dict) -> None:
    targeting = _require(ctx, "media_buy.execution.targeting")
    for key in ("geo_countries", "geo_regions"):
        assert isinstance(targeting.get(key), bool), f"targeting.{key} not a boolean: {targeting!r}"


@then(parsers.parse("the response should include media_buy.portfolio with publisher_domains {domains}"))
def then_portfolio_domains(ctx: dict, domains: str) -> None:
    actual = _require(ctx, "media_buy.portfolio.publisher_domains")
    assert sorted(actual) == sorted(_quoted_list(domains)), f"publisher_domains {actual!r} != {domains}"


@then(parsers.parse("the response should include media_buy.portfolio with primary_channels {channels}"))
def then_portfolio_channels(ctx: dict, channels: str) -> None:
    actual = _require(ctx, "media_buy.portfolio.primary_channels")
    assert sorted(actual) == sorted(_quoted_list(channels)), f"primary_channels {actual!r} != {channels}"


@then("the response should NOT include media_buy details")
def then_no_media_buy(ctx: dict) -> None:
    _assert_absent(ctx, "media_buy")


@then("the response should NOT include account section")
def then_no_account(ctx: dict) -> None:
    _assert_absent(ctx, "account")


# ── Thens: read-only invariant ───────────────────────────────────────


@then("the system state should be unchanged after the response")
def then_state_unchanged(ctx: dict) -> None:
    before = ctx["state_snapshot"]
    after = _db_state_snapshot(ctx["env"])
    assert after == before, f"state changed by a read-only call: before={before} after={after}"


# ── Thens: auth outline ──────────────────────────────────────────────


@then(parsers.re(r"the response should be (?P<outcome>success|AUTH_INVALID)$"))
def then_auth_outcome(ctx: dict, outcome: str) -> None:
    if outcome == "success":
        assert ctx.get("response") is not None, f"expected success, got error: {ctx.get('error')!r}"
        return
    from tests.helpers.envelope_assertions import assert_envelope_shape

    assert ctx.get("error") is not None, "expected AUTH_INVALID, got a success response"
    assert_envelope_shape(
        ctx.get("wire_error_envelope"),
        "AUTH_INVALID",
        recovery="terminal",
    )


@then(
    "a success outcome should carry adcp.major_versions, adcp.idempotency, supported_protocols and the media_buy section"
)
def then_success_carries_sections(ctx: dict) -> None:
    if ctx.get("response") is None:
        return  # conditional Then: only grades success outcomes
    for path in ("adcp.major_versions", "adcp.idempotency", "supported_protocols", "media_buy"):
        _require(ctx, path)


@then("both responses should contain identical capabilities data ignoring last_updated and context")
def then_dual_call_identity(ctx: dict) -> None:
    history = ctx.get("response_history", [])
    assert len(history) == 2, f"expected exactly 2 dispatches, saw {len(history)}"
    dumps = []
    for response, error in history:
        assert response is not None, f"one of the dual calls errored: {error!r}"
        data = response.model_dump(mode="json")
        for volatile in ("last_updated", "context", "context_id", "timestamp"):
            data.pop(volatile, None)
        dumps.append(data)
    assert dumps[0] == dumps[1], f"auth state changed response data: {dumps[0]} != {dumps[1]}"


@then("the response should be a success carrying adcp.major_versions, adcp.idempotency and supported_protocols")
def then_mcp_invalid_token_success(ctx: dict) -> None:
    assert ctx.get("response") is not None, f"expected success, got error: {ctx.get('error')!r}"
    for path in ("adcp.major_versions", "adcp.idempotency", "supported_protocols"):
        _require(ctx, path)


@then("the response should carry the tenant's normal capabilities, not gated on the invalid token")
def then_capabilities_not_gated_on_token(ctx: dict) -> None:
    """INV-4 (AdCP v3.1.1, salesagent-dn2s): capability discovery describes
    the SELLER, not the caller — an invalid/absent token must not degrade
    adapter-derived data. Channels are tenant-resolved (get_adapter_class_for_tenant)
    regardless of whether the presented token resolved a principal, so they
    must equal the harness's tenant-level adapter seed, unaffected by the
    invalid token.

    audience_targeting/conversion_tracking are asserted absent because
    production doesn't emit them at all yet (separate #1592 gap) — NOT
    because a principal is missing.
    """
    from tests.harness.capabilities import DEFAULT_ADAPTER_CHANNELS

    doc = _wire(ctx)
    for path in ("media_buy.audience_targeting", "media_buy.conversion_tracking"):
        assert _at(doc, path) is _MISSING, f"{path} unexpectedly present: {_at(doc, path)!r}"
    channels = _at(doc, "media_buy.portfolio.primary_channels")
    assert channels == DEFAULT_ADAPTER_CHANNELS, (
        f"adapter-derived channels degraded by an invalid token (INV-4 violation): "
        f"expected {DEFAULT_ADAPTER_CHANNELS!r}, got {channels!r}"
    )


# ── Thens: protocols filter (ext-d) ──────────────────────────────────


@then(
    parsers.re(
        r"the response should include the (?P<section>media_buy|signals|governance|sponsored_intelligence|creative) section$"
    )
)
def then_section_present(ctx: dict, section: str) -> None:
    _require(ctx, section)


@then("the response should include adcp, supported_protocols and account as protocol-invariant blocks")
def then_protocol_invariant_blocks(ctx: dict) -> None:
    for path in ("adcp", "supported_protocols", "account"):
        _require(ctx, path)


@then("the response should NOT include the signals, governance, sponsored_intelligence or creative sections")
def then_unrequested_sections_absent(ctx: dict) -> None:
    for section in ("signals", "governance", "sponsored_intelligence", "creative"):
        _assert_absent(ctx, section)


# ── Thens: context echo (ext-e) ──────────────────────────────────────


@then(parsers.parse("the response context should equal {expected}"))
def then_context_equals(ctx: dict, expected: str) -> None:
    actual = _require(ctx, "context")
    assert actual == json.loads(expected), f"context echo mismatch: {actual!r} != {expected}"


@then("the wire response should not contain a context field")
def then_wire_no_context(ctx: dict) -> None:
    doc = _wire(ctx)
    assert "context" not in doc, f"wire response carries a context field: {doc.get('context')!r}"


@then("the wire response context should equal {}")
def then_wire_context_empty(ctx: dict) -> None:
    actual = _require(ctx, "context")
    assert actual == {}, f"wire context expected {{}}, got {actual!r}"


# ── Thens: version negotiation error details ─────────────────────────


@then("the error details should include supported_versions as a non-empty array")
def then_details_supported_versions(ctx: dict) -> None:
    versions = _error_details(ctx).get("supported_versions")
    assert isinstance(versions, list) and versions, f"details.supported_versions not a non-empty array: {versions!r}"


@then(parsers.parse('each supported_versions entry should match pattern "{pattern}"'))
def then_details_versions_pattern(ctx: dict, pattern: str) -> None:
    # The feature escapes backslashes for Gherkin — unescape before matching.
    unescaped = pattern.replace("\\\\", "\\")
    for value in _error_details(ctx)["supported_versions"]:
        assert re.fullmatch(unescaped, value), f"supported_versions entry {value!r} does not match {unescaped!r}"


@then(parsers.parse('the error details should include supported_versions containing "{v1}" and "{v2}"'))
def then_details_versions_containing(ctx: dict, v1: str, v2: str) -> None:
    versions = _error_details(ctx).get("supported_versions", [])
    assert v1 in versions and v2 in versions, f"details.supported_versions {versions!r} missing {v1!r}/{v2!r}"


@then(parsers.parse('the error details should include build_version equal to "{build_version}"'))
def then_details_build_version(ctx: dict, build_version: str) -> None:
    actual = _error_details(ctx).get("build_version")
    assert actual == build_version, f"details.build_version {actual!r} != {build_version!r}"


# ── Thens: outline row→assertion dispatch (features-partitions) ──────

# Row-text → assertion closure. Batch-1 wires ONLY the account.sandbox rows;
# unwired rows raise NotImplementedError → auto-xfail (honest pending state).
_SATISFY_TABLE: dict[str, Any] = {
    "account.sandbox is true": lambda ctx: _expect_flag(ctx, "account.sandbox", "equal to true"),
    "account.sandbox is false": lambda ctx: _expect_flag(ctx, "account.sandbox", "equal to false"),
}


@then(parsers.parse("the response should satisfy {expected_assertion}"))
def then_response_satisfies(ctx: dict, expected_assertion: str) -> None:
    assertion = _SATISFY_TABLE.get(expected_assertion.strip())
    if assertion is None:
        raise NotImplementedError(f"UC-010 assertion row not wired yet: {expected_assertion!r} (#1592)")
    assertion(ctx)
