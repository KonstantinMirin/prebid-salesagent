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

from tests.bdd.steps._outcome_helpers import WIRE_MISSING, wire_absent, wire_dict, wire_field, wire_lookup
from tests.bdd.steps.generic._dispatch import dispatch_request

#: 3.1.1 billing-party enum (dist/schemas/3.1.1/enums/billing-party.json).
BILLING_PARTY_ENUM = {"operator", "agent", "advertiser"}

#: 3.1.1 pricing-model enum (dist/schemas/3.1.1/enums/pricing-model.json).
PRICING_MODEL_ENUM = {"cpm", "vcpm", "cpc", "cpcv", "cpv", "cpp", "cpa", "flat_rate", "time"}

#: 3.1.1 reporting delivery methods enum
#: (get-adcp-capabilities-response.json#/properties/media_buy/properties/reporting_delivery_methods).
REPORTING_DELIVERY_ENUM = {"webhook", "offline"}

#: 3.1.1 media channels enum, in schema order — the 20 canonical values
#: (dist/schemas/3.1.1/enums/channels.json#/enum). primary_channels items $ref
#: this enum; there is no minItems/uniqueItems constraint, so the graded contract
#: is set-equality against these 20 values.
CHANNELS_ENUM = [
    "display",
    "olv",
    "social",
    "search",
    "ctv",
    "linear_tv",
    "radio",
    "streaming_audio",
    "podcast",
    "dooh",
    "ooh",
    "print",
    "cinema",
    "email",
    "gaming",
    "retail_media",
    "influencer",
    "affiliate",
    "product_placement",
    "sponsored_intelligence",
]

# ── Wire helpers ─────────────────────────────────────────────────────


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
@given("the tenant uses the mock adapter with full capabilities configured")
def given_full_capabilities(ctx: dict) -> None:
    """Declare the full-capability tenant. Production has no capability config
    surface yet — this records intent; value asserts xfail until S1/S3 land."""
    _config(ctx)["full"] = True


@given("the tenant supports audience targeting")
def given_supports_audience_targeting(ctx: dict) -> None:
    """Declare audience-targeting support. Production does not emit the
    media_buy.audience_targeting block yet (#1592) — records intent; the
    value asserts xfail until the block lands."""
    _config(ctx)["audience_targeting"] = True


@given("the tenant supports conversion tracking")
def given_supports_conversion_tracking(ctx: dict) -> None:
    """Declare conversion-tracking support. Production does not emit the
    media_buy.conversion_tracking block yet (#1592) — records intent; the
    presence/value asserts xfail until the block lands."""
    _config(ctx)["conversion_tracking"] = True


@given('"creative" is in supported_protocols')
def given_creative_in_supported_protocols(ctx: dict) -> None:
    """Declare the creative protocol. Production advertises only the media_buy
    protocol, so the creative section is not emitted (#1592) — records intent."""
    _config(ctx).setdefault("supported_protocols", []).append("creative")


@given("the tenant declares creative supports_compliance true")
def given_creative_supports_compliance(ctx: dict) -> None:
    """Declare the optional creative.supports_compliance value. Records intent;
    production does not emit the creative section yet (#1592)."""
    _config(ctx)["creative_supports_compliance"] = True


@given("the adapter is unavailable")
def given_adapter_unavailable(ctx: dict) -> None:
    """Adapter factory raises — production degrades to the [display] default channel."""
    ctx["env"].make_adapter_unavailable()


@given("the database query fails")
def given_database_query_fails(ctx: dict) -> None:
    """Publisher-partner DB read fails — production degrades to the placeholder domain."""
    ctx["env"].break_tenant_config_db()


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


@given("the adapter reports all 20 channels enum values")
def given_adapter_all_canonical_channels(ctx: dict) -> None:
    """Seed the adapter with every 3.1.1 channels enum value (channels.json#/enum).
    Production maps each recognized value through CHANNEL_MAPPING onto primary_channels."""
    ctx["env"].set_adapter_channels(list(CHANNELS_ENUM))


@given(parsers.parse("the adapter is in {adapter_state} state"))
def given_adapter_state(ctx: dict, adapter_state: str) -> None:
    """available → default happy adapter (channels + full targeting);
    unavailable → the adapter factory raises, so production degrades to the
    [display] default and drops adapter-derived media_buy sections."""
    if adapter_state == "unavailable":
        ctx["env"].make_adapter_unavailable()
    elif adapter_state != "available":
        raise ValueError(f"unknown adapter_state: {adapter_state!r}")


@given(parsers.parse("the tenant has {capability} configured as {capability_state}"))
def given_capability_configured(ctx: dict, capability: str, capability_state: str) -> None:
    """Record tenant-config capability intent (audience targeting / conversion
    tracking, enabled|disabled). Production has no capability-config surface yet
    (#1592) — this records intent; the media_buy.<section> block is not emitted,
    so the 'present' rows xfail at the Then."""
    if capability_state not in ("enabled", "disabled"):
        raise ValueError(f"unknown capability_state: {capability_state!r}")
    key = capability.strip().replace(" ", "_")
    _config(ctx)[key] = capability_state == "enabled"


@given("the adapter provides full targeting capabilities")
def given_adapter_full_targeting(ctx: dict) -> None:
    """Seed the adapter with every TargetingCapabilities boolean dimension True.
    Production maps geo_countries/geo_regions/geo_metros/geo_postal_areas off this;
    the richer dimensions (age_restriction, language, keyword_targets,
    negative_keywords, geo_proximity) have NO adapter surface and are never built."""
    from dataclasses import fields as _dc_fields

    from src.adapters.base import TargetingCapabilities

    ctx["env"].set_targeting_capabilities(**{f.name: True for f in _dc_fields(TargetingCapabilities)})


@given(parsers.parse("the adapter provides targeting as {config}"))
def given_adapter_targeting_config(ctx: dict, config: str) -> None:
    """Realize an outline-row adapter targeting config (targeting-partitions).

    Only the TargetingCapabilities boolean dimensions have an adapter surface, so
    dotted/native tokens (age_restriction.supported, geo_postal_areas US=[...],
    keyword_targets.*, geo_proximity.*) are recorded as intent — production has no
    way to emit them, which is exactly why those rows are production gaps."""
    from dataclasses import fields as _dc_fields

    from src.adapters.base import TargetingCapabilities

    ctx["targeting_config"] = config
    if "adapter unavailable" in config:
        ctx["env"].make_adapter_unavailable()
        return
    known = {f.name for f in _dc_fields(TargetingCapabilities)}
    if "all dimensions reported" in config:
        ctx["env"].set_targeting_capabilities(**dict.fromkeys(known, True))
        return
    # Default geo_countries/geo_regions on; every nested dimension off unless the
    # row explicitly sets it (so "no nested sub-properties" yields metros/postal absent).
    dims = dict.fromkeys(known, False)
    dims["geo_countries"] = True
    dims["geo_regions"] = True
    for match in re.finditer(r"([a-z_]+(?:\.[a-z_]+)?)\s*=\s*(true|false)", config):
        field = match.group(1).split(".")[-1]
        if field in known:
            dims[field] = match.group(2) == "true"
    ctx["env"].set_targeting_capabilities(**dims)


@given("a tenant is resolvable and adapter and DB are available with all features")
def given_full_degradation_baseline(ctx: dict) -> None:
    """full_response degradation row: happy path (default env — adapter + DB up)."""
    ctx["has_tenant"] = True
    _config(ctx)["full"] = True


@given("a tenant is resolvable but adapter is unavailable")
def given_tenant_adapter_unavailable(ctx: dict) -> None:
    """adapter_fail row: tenant resolves, adapter factory raises → [display] default."""
    ctx["has_tenant"] = True
    ctx["env"].make_adapter_unavailable()


@given("a tenant is resolvable but database query fails")
def given_tenant_db_fails(ctx: dict) -> None:
    """db_fail row: tenant resolves, publisher-partner DB read fails → placeholder domain."""
    ctx["has_tenant"] = True
    ctx["env"].break_tenant_config_db()


@given("a tenant is resolvable but both adapter and DB fail")
def given_tenant_adapter_and_db_fail(ctx: dict) -> None:
    """adapter_and_db_fail row: both degrade — [display] channels + placeholder domain."""
    ctx["has_tenant"] = True
    ctx["env"].make_adapter_unavailable()
    ctx["env"].break_tenant_config_db()


@given("a tenant is resolvable but no auth principal available")
def given_tenant_no_principal(ctx: dict) -> None:
    """no_principal row: tenant resolves, caller is principal-less (anonymous identity).
    Per INV-4 the adapter is tenant-only/principal-free, so adapter-derived channels
    are NOT degraded by the missing principal — the [display] expectation is the gap."""
    ctx["has_tenant"] = True
    ctx["identity"] = ctx["env"].anonymous_identity()


@given(
    parsers.re(
        r"a tenant is resolvable but adapter unavailable or "
        r"(?P<capability>audience targeting|conversion tracking) disabled$"
    )
)
def given_tenant_section_absent(ctx: dict, capability: str) -> None:
    """audience_targeting_absent / conversion_tracking_absent rows: model the
    'adapter unavailable' leg (the capabilities builder never emits these blocks
    regardless, so they are absent on the wire)."""
    ctx["has_tenant"] = True
    ctx["env"].make_adapter_unavailable()
    _config(ctx)[capability.replace(" ", "_")] = False


@given("a tenant is resolvable but creative not in supported_protocols")
def given_tenant_creative_absent(ctx: dict) -> None:
    """creative_absent row: production advertises only the media_buy protocol, so
    the creative section is never emitted."""
    ctx["has_tenant"] = True
    _config(ctx)["supported_protocols"] = ["media_buy"]


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
    assert 3 in wire_field(ctx, "adcp.major_versions")


@then(
    "adcp.idempotency.supported should be exactly true or false, and when false "
    "replay_ttl_seconds and in_flight_max_seconds should be absent"
)
def then_idempotency_discriminator(ctx: dict) -> None:
    """oneOf discriminator invariant (get-adcp-capabilities-response.json
    #/properties/adcp/properties/idempotency/oneOf): supported is the boolean
    discriminator; on the IdempotencyUnsupported branch (supported=false) the
    schema's `not.anyOf` forbids replay_ttl_seconds and in_flight_max_seconds —
    they "have no meaning without replay support"."""
    idempotency = wire_dict(ctx, "adcp.idempotency")
    supported = idempotency.get("supported")
    assert isinstance(supported, bool), f"idempotency.supported not a boolean: {supported!r}"
    if supported is False:
        for forbidden in ("replay_ttl_seconds", "in_flight_max_seconds"):
            assert forbidden not in idempotency, (
                f"IdempotencyUnsupported (supported=false) must omit {forbidden}: {idempotency!r}"
            )


@then("adcp.idempotency should be present in the response")
def then_idempotency_present(ctx: dict) -> None:
    """adcp.idempotency is REQUIRED (get-adcp-capabilities-response.json
    #/properties/adcp/required includes idempotency; "Clients MUST NOT assume a
    default"). wire_dict pins present AND non-null AND a JSON object."""
    wire_dict(ctx, "adcp.idempotency")


@then("adcp.idempotency.supported should equal true")
def then_idempotency_supported_true(ctx: dict) -> None:
    """oneOf IdempotencySupported: supported is the const-true discriminator
    (get-adcp-capabilities-response.json#/properties/adcp/properties/idempotency/oneOf/0)."""
    value = wire_field(ctx, "adcp.idempotency.supported")
    assert value is True, f"idempotency.supported expected true, got {value!r}"


@then("adcp.idempotency.replay_ttl_seconds should be an integer between 3600 and 604800")
def then_idempotency_ttl_range(ctx: dict) -> None:
    """IdempotencySupported requires replay_ttl_seconds, integer in [3600, 604800]."""
    ttl = wire_field(ctx, "adcp.idempotency.replay_ttl_seconds")
    assert isinstance(ttl, int) and not isinstance(ttl, bool), f"replay_ttl_seconds not an integer: {ttl!r}"
    assert 3600 <= ttl <= 604800, f"replay_ttl_seconds {ttl!r} outside [3600, 604800]"


@then("the response should include adcp.supported_versions as a non-empty array")
def then_supported_versions_nonempty(ctx: dict) -> None:
    versions = wire_field(ctx, "adcp.supported_versions")
    assert isinstance(versions, list) and versions, f"adcp.supported_versions not a non-empty array: {versions!r}"


@then(parsers.parse('each value in adcp.supported_versions should match pattern "{pattern}"'))
def then_supported_versions_pattern(ctx: dict, pattern: str) -> None:
    for value in wire_field(ctx, "adcp.supported_versions"):
        assert re.fullmatch(pattern, value), f"supported_versions entry {value!r} does not match {pattern!r}"


@then(parsers.parse('the response should include supported_protocols containing "{protocol}"'))
def then_supported_protocols_contains(ctx: dict, protocol: str) -> None:
    assert protocol in wire_field(ctx, "supported_protocols")


@then(parsers.parse('supported_protocols should contain "{protocol}"'))
def then_supported_protocols_contains_short(ctx: dict, protocol: str) -> None:
    assert protocol in wire_field(ctx, "supported_protocols")


@then("last_updated should be an RFC 3339 date-time string")
@then("last_updated should parse as an RFC 3339 date-time value")
def then_last_updated_valid(ctx: dict) -> None:
    """Format pinned to the schema keyword (last_updated: format date-time).
    The value must be a string that parses as an RFC 3339 / JSON-Schema
    date-time (e.g. "2025-10-14T14:25:30Z")."""
    from datetime import datetime

    raw = wire_field(ctx, "last_updated")
    assert isinstance(raw, str), f"last_updated not a string: {raw!r}"
    datetime.fromisoformat(raw.replace("Z", "+00:00"))  # raises on malformed


# ── Thens: account block ─────────────────────────────────────────────


def _assert_billing_party_array(value: Any) -> None:
    assert isinstance(value, list) and value, f"supported_billing not a non-empty array: {value!r}"
    assert set(value) <= BILLING_PARTY_ENUM, f"supported_billing carries non-enum values: {value!r}"


@then("account.supported_billing should be a non-empty array")
def then_supported_billing_nonempty(ctx: dict) -> None:
    value = wire_field(ctx, "account.supported_billing")
    assert isinstance(value, list) and value, f"supported_billing not a non-empty array: {value!r}"


@then(parsers.parse("account.supported_billing should equal {expected_set}"))
def then_supported_billing_equals(ctx: dict, expected_set: str) -> None:
    expected = [part.strip() for part in expected_set.strip("[]").split(",") if part.strip()]
    value = wire_field(ctx, "account.supported_billing")
    assert sorted(value) == sorted(expected), f"supported_billing {value!r} != {expected!r}"


@then('each supported_billing value should be one of "operator", "agent", "advertiser"')
def then_supported_billing_enum(ctx: dict) -> None:
    _assert_billing_party_array(wire_field(ctx, "account.supported_billing"))


@then(parsers.parse("account.sandbox should equal {expected}"))
def then_account_sandbox_equals(ctx: dict, expected: str) -> None:
    """account.sandbox is a boolean (default false). Pinned to the exact
    scenario value — no silent-skip on missing config."""
    value = wire_field(ctx, "account.sandbox")
    want = json.loads(expected)
    assert value is want, f"account.sandbox expected {want!r}, got {value!r}"


def _expect_flag(ctx: dict, path: str, expected: str) -> None:
    """Grade an outline <expected> column: 'equal to true/false' | 'absent' |
    'absent or false' | 'equal to "..." as a URI'."""
    value = wire_lookup(ctx, path)
    if expected == "absent":
        assert value is WIRE_MISSING, f"{path} unexpectedly present: {value!r}"
    elif expected == "absent or false":
        assert value is WIRE_MISSING or value is False, f"{path} expected absent-or-false, got {value!r}"
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
    account = wire_field(ctx, "account")
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
        wire_absent(ctx, "account")
        return
    account = wire_field(ctx, "account")
    _assert_billing_party_array(account.get("supported_billing"))
    if state.startswith("present with supported_billing only"):
        extras = set(account) - {"supported_billing"}
        assert not extras, f"degraded account block carries optional fields: {sorted(extras)}"


@then("a present account section should include supported_billing as a non-empty array of billing-party enum values")
def then_present_account_billing(ctx: dict) -> None:
    account = wire_lookup(ctx, "account")
    if account is WIRE_MISSING:
        return  # conditional Then: only grades a present block
    _assert_billing_party_array(account.get("supported_billing"))


# ── Thens: media_buy block (batch-1 subset) ──────────────────────────

_FEATURE_FLAGS = (
    "inline_creative_management",
    "property_list_filtering",
    "catalog_management",
    "committed_metrics_supported",
)


@then(parsers.parse("media_buy.features should have boolean flags {flags}"))
def then_features_boolean_flags(ctx: dict, flags: str) -> None:
    """media-buy-features.json: 4 named flags, all boolean, additionalProperties
    boolean, none required. The per-flag VALUE is a production choice (spec-silent),
    so the graded contract is the shape: every named flag present is a boolean, and
    every property on the object (named or additional) is a boolean."""
    features = wire_field(ctx, "media_buy.features")
    assert isinstance(features, dict), f"media_buy.features not an object: {features!r}"
    named = [name.strip() for name in re.split(r",|\band\b", flags) if name.strip()]
    assert set(named) == set(_FEATURE_FLAGS), f"scenario names unexpected feature flags: {named!r}"
    for key, value in features.items():
        assert isinstance(value, bool), f"features.{key} not a boolean: {value!r}"


@then("media_buy.supported_pricing_models should be a non-empty unique array of pricing-model enum values")
def then_pricing_models_shape(ctx: dict) -> None:
    """supported_pricing_models: minItems 1, uniqueItems, items ∈ pricing-model enum.
    The exact SET is config-derived (spec: "products may support a subset") — a
    production config surface (#1592), so only the spec-pinned shape is graded here."""
    models = wire_field(ctx, "media_buy.supported_pricing_models")
    assert isinstance(models, list) and models, f"supported_pricing_models not a non-empty array: {models!r}"
    assert len(models) == len(set(models)), f"supported_pricing_models has duplicates: {models!r}"
    invalid = set(models) - PRICING_MODEL_ENUM
    assert not invalid, f"supported_pricing_models carries non-enum values: {sorted(invalid)}"


@then(parsers.parse("each pricing model should be one of {allowed}"))
def then_pricing_models_enum(ctx: dict, allowed: str) -> None:
    allowed_set = set(_quoted_list(allowed))
    models = wire_field(ctx, "media_buy.supported_pricing_models")
    invalid = set(models) - allowed_set
    assert not invalid, f"supported_pricing_models has values outside {sorted(allowed_set)}: {sorted(invalid)}"


@then("media_buy.supported_pricing_models should contain no duplicates")
def then_pricing_models_no_duplicates(ctx: dict) -> None:
    models = wire_field(ctx, "media_buy.supported_pricing_models")
    assert len(models) == len(set(models)), f"supported_pricing_models has duplicates: {models!r}"


@then(parsers.parse("media_buy.reporting_delivery_methods should be a non-empty unique subset of {allowed}"))
def then_reporting_methods_subset(ctx: dict, allowed: str) -> None:
    """reporting_delivery_methods: minItems 1, uniqueItems, items ∈ {webhook, offline}.
    The exact SET is a seller config choice (spec-silent on value) — only the
    spec-pinned shape/enum is graded (#1592 for the emission itself)."""
    allowed_set = set(_quoted_list(allowed))
    assert allowed_set <= REPORTING_DELIVERY_ENUM, f"scenario allows non-enum reporting methods: {allowed_set!r}"
    methods = wire_field(ctx, "media_buy.reporting_delivery_methods")
    assert isinstance(methods, list) and methods, f"reporting_delivery_methods not a non-empty array: {methods!r}"
    assert len(methods) == len(set(methods)), f"reporting_delivery_methods has duplicates: {methods!r}"
    invalid = set(methods) - allowed_set
    assert not invalid, f"reporting_delivery_methods carries values outside {sorted(allowed_set)}: {sorted(invalid)}"


@then("media_buy.execution.targeting should include geo_countries and geo_regions as booleans")
def then_targeting_geo_booleans(ctx: dict) -> None:
    targeting = wire_field(ctx, "media_buy.execution.targeting")
    for key in ("geo_countries", "geo_regions"):
        assert isinstance(targeting.get(key), bool), f"targeting.{key} not a boolean: {targeting!r}"


def _assert_wire_equals(ctx: dict, path: str, expected: str) -> None:
    """Exact-equality oracle on a dotted success-path wire field.

    Shared by every "<block>.<field> should equal <json>" Then (targeting,
    audience_targeting, conversion_tracking, creative) — one loud-guarded
    dual-assert read (wire_field) plus a JSON-parsed exact compare, so the four
    step families do not each hand-roll the same three lines (DRY)."""
    actual = wire_field(ctx, path)
    want = json.loads(expected)
    assert actual == want, f"{path} expected {want!r}, got {actual!r}"


@then(parsers.parse("media_buy.execution.targeting.{field} should equal {expected}"))
def then_targeting_field_equals(ctx: dict, field: str, expected: str) -> None:
    """Exact value on a targeting sub-field (e.g. geo_countries should equal true).
    targeting.<field> types are booleans/objects per the response schema."""
    _assert_wire_equals(ctx, f"media_buy.execution.targeting.{field}", expected)


@then(
    parsers.re(
        r'media_buy\.execution\.targeting\.geo_postal_areas should be a country-keyed map where (?P<country>[A-Z]{2}) contains "(?P<token>[a-z_]+)"$'
    )
)
def then_geo_postal_native_map(ctx: dict, country: str, token: str) -> None:
    """geo_postal_areas is the NATIVE country-keyed map (postal-area-support.json:
    named country props US/GB/CA/... plus additionalProperties = array items enum
    [postal_code, custom]) — NOT the deprecated country-fused boolean aliases
    (us_zip/de_plz, marked deprecated: true). Grades the native shape: the given
    country key maps to an array containing the given item."""
    postal = wire_field(ctx, "media_buy.execution.targeting.geo_postal_areas")
    assert isinstance(postal, dict), f"geo_postal_areas not an object: {postal!r}"
    assert country in postal, f"geo_postal_areas has no native country key {country!r}: {sorted(postal)}"
    assert token in postal[country], f"geo_postal_areas.{country} does not contain {token!r}: {postal[country]!r}"


@then(parsers.parse("media_buy.execution.targeting should not contain {names}"))
def then_targeting_absent_keys(ctx: dict, names: str) -> None:
    """Removed-in-3.1 dimensions: device_platform / device_type ("implied by
    media_buy support") and audience_include / audience_exclude (moved to the
    presence of media_buy.audience_targeting) MUST NOT appear on targeting."""
    targeting = wire_field(ctx, "media_buy.execution.targeting")
    forbidden = [name.strip() for name in re.split(r",|\bor\b|\band\b", names) if name.strip()]
    present = [name for name in forbidden if name in targeting]
    assert not present, f"targeting carries removed dimensions {present}: {sorted(targeting)}"


@then(parsers.parse("media_buy.audience_targeting.{field} should equal {expected}"))
def then_audience_field_equals(ctx: dict, field: str, expected: str) -> None:
    """Exact value on an audience_targeting sub-field. Required members
    (supported_identifier_types, minimum_audience_size) plus the optional
    members are each pinned to the scenario fixture value."""
    _assert_wire_equals(ctx, f"media_buy.audience_targeting.{field}", expected)


@then(parsers.parse("media_buy.{section} should be present"))
def then_media_buy_section_present(ctx: dict, section: str) -> None:
    """3.1.1 presence-indicates-support model: content_standards /
    conversion_tracking / audience_targeting are objects whose PRESENCE is the
    support signal (the equivalent features.* flags were removed in 3.0). wire_dict
    pins the dual assert — present AND non-null AND a JSON object. Covers each
    presence-object under media_buy with one grounded helper (DRY)."""
    wire_dict(ctx, f"media_buy.{section}")


@then(
    parsers.re(
        r"the media_buy\.(?P<section>audience_targeting|conversion_tracking) "
        r"section should be (?P<state>absent|present)$"
    )
)
def then_media_buy_section_state(ctx: dict, section: str, state: str) -> None:
    """Adapter-dependence of the audience_targeting / conversion_tracking blocks
    (production choice; the spec is silent on WHY a section is present). 'present'
    pins the dual assert (non-null JSON object); 'absent' pins wire-key absence —
    a JSON null would be schema-invalid for these optional-object fields, so it is
    NOT treated as absent."""
    path = f"media_buy.{section}"
    if state == "absent":
        wire_absent(ctx, path)
    else:
        wire_dict(ctx, path)


@then("a present audience_targeting section should include supported_identifier_types and minimum_audience_size")
def then_present_audience_required_members(ctx: dict) -> None:
    """Conditional required-member grade: audience_targeting.required =
    [supported_identifier_types, minimum_audience_size]
    (get-adcp-capabilities-response.json#/properties/media_buy/properties/audience_targeting/required).
    Only grades a present block (mirrors then_present_account_billing)."""
    section = wire_lookup(ctx, "media_buy.audience_targeting")
    if section is WIRE_MISSING:
        return  # conditional Then: only grades a present block
    assert isinstance(section, dict), f"audience_targeting not an object: {section!r}"
    for member in ("supported_identifier_types", "minimum_audience_size"):
        assert member in section, f"present audience_targeting missing required member {member!r}: {section}"


@then(parsers.parse("media_buy.conversion_tracking.{field} should equal {expected}"))
def then_conversion_field_equals(ctx: dict, field: str, expected: str) -> None:
    """Exact value on a conversion_tracking sub-field. The block has no required
    members; each declared sub-field is pinned to its scenario fixture value —
    items drawn from the pinned event-type / uid-type / action-source enums,
    attribution_windows items are window objects with a required post_click array."""
    _assert_wire_equals(ctx, f"media_buy.conversion_tracking.{field}", expected)


@then(parsers.parse("creative.{field} should equal {expected}"))
def then_creative_field_equals(ctx: dict, field: str, expected: str) -> None:
    """Exact value on a creative sub-field (e.g. supports_compliance should equal
    true). Pinned to the declared fixture value — the creative block is optional
    and only present when creative is in supported_protocols."""
    _assert_wire_equals(ctx, f"creative.{field}", expected)


@then(parsers.parse("the response should include media_buy.portfolio with publisher_domains {domains}"))
def then_portfolio_domains(ctx: dict, domains: str) -> None:
    actual = wire_field(ctx, "media_buy.portfolio.publisher_domains")
    assert sorted(actual) == sorted(_quoted_list(domains)), f"publisher_domains {actual!r} != {domains}"


@then(parsers.parse("the response should include media_buy.portfolio with primary_channels {channels}"))
def then_portfolio_channels(ctx: dict, channels: str) -> None:
    actual = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert sorted(actual) == sorted(_quoted_list(channels)), f"primary_channels {actual!r} != {channels}"


@then("primary_channels should equal the channels enum's 20 canonical values")
def then_primary_channels_all_canonical(ctx: dict) -> None:
    """Every 3.1.1 channels enum value round-trips onto primary_channels.
    primary_channels items $ref channels.json#/enum (20 values, no minItems/
    uniqueItems) — so the graded contract is set-equality against all 20.
    Strict xfail today: CHANNEL_MAPPING omits sponsored_intelligence, so the
    20th value is dropped and the wire carries only 19."""
    actual = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert sorted(actual) == sorted(CHANNELS_ENUM), (
        f"primary_channels is not the full 20-value channels enum: "
        f"missing {sorted(set(CHANNELS_ENUM) - set(actual))}, extra {sorted(set(actual) - set(CHANNELS_ENUM))}"
    )


@then("the wire response should not contain a media_buy key")
def then_no_media_buy(ctx: dict) -> None:
    """Absence asserted as wire-key absence — top-level required is
    [adcp, supported_protocols], so media_buy is optional and a minimal response
    omits the key entirely (there is no `media_buy.details` wire key)."""
    wire_absent(ctx, "media_buy")


@then("the wire response should not contain an adcp_error field")
def then_no_adcp_error(ctx: dict) -> None:
    """A successful (degraded-but-valid) response carries no envelope error signal:
    protocol-envelope adcp_error is the transport-level error field for FATAL task
    failures only, so it is absent on a non-failure."""
    wire_absent(ctx, "adcp_error")


@then("the response should pass schema validation for get-adcp-capabilities-response")
def then_schema_valid(ctx: dict) -> None:
    """Storyboard response_schema check: the serialized wire MUST conform to
    get-adcp-capabilities-response.json. Re-validate the actual wire body through
    the pinned GetAdcpCapabilitiesResponse model (generated from that schema) — a
    degraded response that dropped a required field or emitted an out-of-constraint
    value raises ValidationError here, so the assertion is non-vacuous."""
    from adcp.types import GetAdcpCapabilitiesResponse

    GetAdcpCapabilitiesResponse.model_validate(wire_dict(ctx))


@then("the response should NOT include account section")
def then_no_account(ctx: dict) -> None:
    wire_absent(ctx, "account")


# ── Thens: read-only invariant ───────────────────────────────────────


@then("the row counts of tenants, principals, publisher_partners and media_buys should equal their pre-request values")
def then_state_unchanged(ctx: dict) -> None:
    """Read-only invariant with a concrete observable set: the four mutable
    tables a capabilities call could touch (tenants, principals,
    publisher_partners, media_buys) — snapshotted by _db_state_snapshot."""
    before = ctx["state_snapshot"]
    after = _db_state_snapshot(ctx["env"])
    assert after == before, f"state changed by a read-only call: before={before} after={after}"


# ── Thens: auth outline ──────────────────────────────────────────────


@then(parsers.re(r"the response should be (?P<outcome>success|AUTH_INVALID)$"))
def then_auth_outcome(ctx: dict, outcome: str) -> None:
    if outcome == "success":
        # A success outcome is a non-error completed discovery envelope: no wire
        # error envelope was produced (auth accepted / treated-as-absent) and the
        # spec-required top-level blocks are on the wire (top-level required is
        # [adcp, supported_protocols]). The fuller section shape is graded by the
        # companion "a success outcome should carry ..." Then.
        assert ctx.get("error") is None, f"expected success, got error: {ctx.get('error')!r}"
        assert ctx.get("wire_error_envelope") is None, (
            f"expected success, got a wire error envelope: {ctx.get('wire_error_envelope')!r}"
        )
        for path in ("adcp", "supported_protocols"):
            wire_field(ctx, path)
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
        wire_field(ctx, path)


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
        wire_field(ctx, path)


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

    for path in ("media_buy.audience_targeting", "media_buy.conversion_tracking"):
        wire_absent(ctx, path)
    channels = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert channels == DEFAULT_ADAPTER_CHANNELS, (
        f"adapter-derived channels degraded by an invalid token (INV-4 violation): "
        f"expected {DEFAULT_ADAPTER_CHANNELS!r}, got {channels!r}"
    )


@then(parsers.re(r'the wire error message should contain "(?P<first>[^"]+)" and "(?P<second>[^"]+)"$'))
def then_wire_error_message_contains(ctx: dict, first: str, second: str) -> None:
    """errors[0].message on the wire envelope must carry BOTH pinned substrings
    (case-insensitive). core/error.json message is a free string, so the spec
    cannot pin content — the substrings are pinned to production's ACTUAL
    AUTH_INVALID wording: resolved_identity.py "Authentication token is invalid
    for tenant '...'" and adcp_a2a_server.py "Authentication token is invalid or
    expired." both contain "token" and "invalid". Requiring both rejects the
    AUTH_REQUIRED missing-credential wording ("authentication required")."""
    envelope = ctx.get("wire_error_envelope") or ctx.get("synthesized_error_envelope")
    assert isinstance(envelope, dict), f"no wire error envelope captured (error={ctx.get('error')!r})"
    errors = envelope.get("errors") or [{}]
    message = errors[0].get("message") or ""
    assert message, f"errors[0].message is empty on the wire envelope: {envelope}"
    lowered = message.lower()
    for substring in (first, second):
        assert substring.lower() in lowered, (
            f"wire error message {message!r} is missing the pinned substring {substring!r}"
        )


# ── Thens: protocols filter (ext-d) ──────────────────────────────────


@then(
    parsers.re(
        r"the response should include the (?P<section>media_buy|signals|governance|sponsored_intelligence|creative) section$"
    )
)
def then_section_present(ctx: dict, section: str) -> None:
    wire_field(ctx, section)


@then("the response should include adcp, supported_protocols and account as protocol-invariant blocks")
def then_protocol_invariant_blocks(ctx: dict) -> None:
    for path in ("adcp", "supported_protocols", "account"):
        wire_field(ctx, path)


@then("the response should NOT include the signals, governance, sponsored_intelligence or creative sections")
def then_unrequested_sections_absent(ctx: dict) -> None:
    for section in ("signals", "governance", "sponsored_intelligence", "creative"):
        wire_absent(ctx, section)


# ── Thens: context echo (ext-e) ──────────────────────────────────────


@then(parsers.parse("the response context should equal {expected}"))
def then_context_equals(ctx: dict, expected: str) -> None:
    actual = wire_field(ctx, "context")
    assert actual == json.loads(expected), f"context echo mismatch: {actual!r} != {expected}"


@then("the wire response should not contain a context field")
def then_wire_no_context(ctx: dict) -> None:
    wire_absent(ctx, "context")


@then("the wire response context should equal {}")
def then_wire_context_empty(ctx: dict) -> None:
    actual = wire_field(ctx, "context")
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


# ── Thens: targeting outline row→assertion dispatch (targeting-partitions) ──

#: The 9 canonical targeting property names
#: (get-adcp-capabilities-response.json#/.../targeting/properties).
_NINE_TARGETING_KEYS = {
    "geo_countries",
    "geo_regions",
    "geo_metros",
    "geo_postal_areas",
    "age_restriction",
    "language",
    "keyword_targets",
    "negative_keywords",
    "geo_proximity",
}

_TARGETING_PREFIX = "media_buy.execution.targeting"


def _tp_full_adapter(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert set(targeting) == _NINE_TARGETING_KEYS, f"targeting keys != 9 canonical: {sorted(targeting)}"
    assert targeting["geo_countries"] is True and targeting["geo_regions"] is True, (
        f"geo flags not both true: {targeting!r}"
    )


def _tp_defaults(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert targeting == {"geo_countries": True, "geo_regions": True}, f"targeting != production default: {targeting!r}"


def _tp_partial(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert targeting.get("geo_countries") is True, f"geo_countries not true: {targeting!r}"
    assert targeting.get("geo_regions") is False, f"geo_regions not false: {targeting!r}"
    assert targeting.get("age_restriction", {}).get("supported") is True, (
        f"age_restriction.supported not true: {targeting!r}"
    )
    stray = {"geo_metros", "geo_postal_areas"} & set(targeting)
    assert not stray, f"partial config leaked geo keys {sorted(stray)}: {sorted(targeting)}"


def _tp_nested_populated(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert targeting.get("geo_metros") == {"nielsen_dma": True}, (
        f"geo_metros != {{nielsen_dma: true}}: {targeting.get('geo_metros')!r}"
    )
    postal = targeting.get("geo_postal_areas") or {}
    assert "US" in postal and "zip" in postal["US"], f"geo_postal_areas US containing zip not present: {postal!r}"


def _tp_nested_absent(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    stray = {"geo_metros", "geo_postal_areas"} & set(targeting)
    assert not stray, f"geo_metros/geo_postal_areas should be absent: {sorted(targeting)}"


def _tp_keyword(ctx: dict) -> None:
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert targeting.get("keyword_targets", {}).get("supported_match_types") == ["broad", "phrase", "exact"], (
        f"keyword_targets match types wrong: {targeting.get('keyword_targets')!r}"
    )
    assert targeting.get("negative_keywords", {}).get("supported_match_types") == ["exact"], (
        f"negative_keywords match types wrong: {targeting.get('negative_keywords')!r}"
    )


def _tp_postal_legacy(ctx: dict) -> None:
    postal = wire_field(ctx, f"{_TARGETING_PREFIX}.geo_postal_areas")
    assert isinstance(postal, dict) and "DE" in postal and "plz" in postal["DE"], (
        f"native DE containing plz not present: {postal!r}"
    )


#: Targeting outline expected-column → assertion. Rows production satisfies
#: (adapter_unavailable_defaults, nested_absent) pass; the rest execute the real
#: assertion and fail on dimensions the builder never emits (#1592 gaps, marked
#: strict via conftest _SELECTIVE_XFAIL).
_TARGETING_SATISFY: dict[str, Any] = {
    "targeting has exactly the keys geo_countries, geo_regions, geo_metros, geo_postal_areas, "
    "age_restriction, language, keyword_targets, negative_keywords and geo_proximity with "
    "geo_countries true and geo_regions true": _tp_full_adapter,
    "targeting equals exactly {geo_countries: true, geo_regions: true}": _tp_defaults,
    "geo_countries true, geo_regions false, age_restriction.supported true, no other geo keys": _tp_partial,
    'geo_metros equals {nielsen_dma: true} and geo_postal_areas has US containing "zip"': _tp_nested_populated,
    "geo_metros and geo_postal_areas absent from targeting": _tp_nested_absent,
    "age_restriction equals {supported: true, verification_methods: [id_document]}": lambda ctx: _assert_wire_equals(
        ctx, f"{_TARGETING_PREFIX}.age_restriction", '{"supported": true, "verification_methods": ["id_document"]}'
    ),
    "keyword_targets match types equal [broad, phrase, exact] and negative_keywords match types equal [exact]": _tp_keyword,
    "geo_proximity equals {radius: true, travel_time: true, geometry: false, transport_modes: [driving, walking]}": lambda ctx: (
        _assert_wire_equals(
            ctx,
            f"{_TARGETING_PREFIX}.geo_proximity",
            '{"radius": true, "travel_time": true, "geometry": false, "transport_modes": ["driving", "walking"]}',
        )
    ),
    "geo_postal_areas equals {DE: [plz], CH: [plz], AT: [plz]}": lambda ctx: _assert_wire_equals(
        ctx, f"{_TARGETING_PREFIX}.geo_postal_areas", '{"DE": ["plz"], "CH": ["plz"], "AT": ["plz"]}'
    ),
    'geo_postal_areas has native DE containing "plz" and MAY carry the deprecated de_plz alias': _tp_postal_legacy,
}


@then(parsers.parse("media_buy.execution.targeting should satisfy {expected_targeting}"))
def then_targeting_satisfies(ctx: dict, expected_targeting: str) -> None:
    assertion = _TARGETING_SATISFY.get(expected_targeting.strip())
    if assertion is None:
        raise NotImplementedError(f"UC-010 targeting assertion row not wired: {expected_targeting!r} (#1592)")
    assertion(ctx)


# ── Thens: degradation + features-partitions outline dispatch ────────


def _deg_full_response(ctx: dict) -> None:
    wire = wire_dict(ctx)
    for key in ("adcp", "supported_protocols", "account", "media_buy", "last_updated"):
        assert key in wire, f"full_response missing top-level {key!r}: {sorted(wire)}"
    billing = wire["account"].get("supported_billing")
    assert isinstance(billing, list) and billing, f"account.supported_billing not non-empty: {billing!r}"
    assert isinstance(wire["adcp"].get("idempotency"), dict), f"adcp.idempotency absent: {wire['adcp']!r}"


def _deg_no_tenant(ctx: dict) -> None:
    wire = wire_dict(ctx)
    assert set(wire) <= {"adcp", "supported_protocols"}, f"no_tenant top-level not minimal: {sorted(wire)}"
    adcp = wire["adcp"]
    for key in ("major_versions", "supported_versions", "idempotency"):
        assert key in adcp, f"no_tenant adcp missing {key!r}: {sorted(adcp)}"


def _deg_display_default(ctx: dict) -> None:
    channels = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert channels == ["display"], f"primary_channels not the [display] default: {channels!r}"
    targeting = wire_field(ctx, _TARGETING_PREFIX)
    assert targeting == {"geo_countries": True, "geo_regions": True}, (
        f"targeting not the degraded default: {targeting!r}"
    )
    for path in (
        "media_buy.reporting_delivery_methods",
        "media_buy.audience_targeting",
        "media_buy.conversion_tracking",
    ):
        wire_absent(ctx, path)


def _assert_placeholder_domain(ctx: dict) -> None:
    domains = wire_field(ctx, "media_buy.portfolio.publisher_domains")
    assert isinstance(domains, list) and len(domains) == 1 and str(domains[0]).endswith(".example.com"), (
        f"publisher_domains not the single placeholder domain: {domains!r}"
    )


def _deg_db_fail(ctx: dict) -> None:
    _assert_placeholder_domain(ctx)
    channels = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert channels == ["display", "social", "ctv"], f"adapter channels degraded on a DB-only failure: {channels!r}"


def _deg_adapter_and_db_fail(ctx: dict) -> None:
    channels = wire_field(ctx, "media_buy.portfolio.primary_channels")
    assert channels == ["display"], f"primary_channels not the [display] default: {channels!r}"
    _assert_placeholder_domain(ctx)
    for path in ("media_buy.audience_targeting", "media_buy.conversion_tracking"):
        wire_absent(ctx, path)


def _deg_account_degraded(ctx: dict) -> None:
    account = wire_field(ctx, "account")
    billing = account.get("supported_billing")
    assert isinstance(billing, list) and billing, f"degraded account.supported_billing not non-empty: {billing!r}"
    extras = set(account) - {"supported_billing"}
    assert not extras, f"degraded account carries optional fields: {sorted(extras)}"


# Row-text → assertion closure (features-partitions account.sandbox + degradation rows).
# Rows production satisfies pass; production-gap rows execute the real assertion and
# fail (strict per-row xfail in conftest _SELECTIVE_XFAIL).
_SATISFY_TABLE: dict[str, Any] = {
    "account.sandbox is true": lambda ctx: _expect_flag(ctx, "account.sandbox", "equal to true"),
    "account.sandbox is false": lambda ctx: _expect_flag(ctx, "account.sandbox", "equal to false"),
    "top-level keys include adcp, supported_protocols, account, media_buy and last_updated "
    "with account.supported_billing non-empty and adcp.idempotency present": _deg_full_response,
    "only adcp and supported_protocols at top level, with adcp carrying major_versions, "
    "supported_versions and idempotency": _deg_no_tenant,
    "primary_channels equals [display] and targeting equals exactly {geo_countries: true, "
    "geo_regions: true} with no reporting_delivery_methods, audience_targeting or conversion_tracking": _deg_display_default,
    "publisher_domains equals the placeholder domain and primary_channels equals [display, social, ctv]": _deg_db_fail,
    "primary_channels equals [display] and publisher_domains equals the placeholder domain, "
    "adapter-dependent sections absent": _deg_adapter_and_db_fail,
    "account present with non-empty supported_billing and no optional account fields": _deg_account_degraded,
    "media_buy.audience_targeting absent": lambda ctx: wire_absent(ctx, "media_buy.audience_targeting"),
    "media_buy.conversion_tracking absent": lambda ctx: wire_absent(ctx, "media_buy.conversion_tracking"),
    "creative section absent": lambda ctx: wire_absent(ctx, "creative"),
}


@then(parsers.parse("the response should satisfy {expected_assertion}"))
def then_response_satisfies(ctx: dict, expected_assertion: str) -> None:
    assertion = _SATISFY_TABLE.get(expected_assertion.strip())
    if assertion is None:
        raise NotImplementedError(f"UC-010 assertion row not wired yet: {expected_assertion!r} (#1592)")
    assertion(ctx)


# ══════════════════════════════════════════════════════════════════════════
# Batch 5 (salesagent-scgh): v3.1.1 signing / brand / reporting / measurement
#
# reporting_delivery_methods, offline_delivery_protocols, webhook_signing, the
# brand block, the identity signing posture and the measurement block are NOT
# built by the capabilities builder (src/core/tools/capabilities.py emits only
# adcp / supported_protocols / specialisms / media_buy{features,execution}).
# The Givens record declared intent; the Thens grade the exact v3.1.1-pinned
# shape on the wire. Rows production already satisfies (polling-only absence,
# the no-emission webhook row, the valid identity row) PASS; the rest execute
# the real assertion and fail on the unemitted block — strict per-row/per-tag
# xfail in conftest (_SELECTIVE_XFAIL / _XFAIL_TAGS), never a dormant skip.
# ══════════════════════════════════════════════════════════════════════════


#: 3.1.1 cloud-storage-protocol enum (enums/cloud-storage-protocol.json).
CLOUD_STORAGE_PROTOCOL_ENUM = {"s3", "gcs", "azure_blob"}

#: 3.1.1 vendor-metric-id constraints (core/vendor-metric-id.json).
_VENDOR_METRIC_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_bracket_list(token: str) -> list[str]:
    """Parse a Gherkin '[a, b]' fragment into a list of bare string tokens."""
    inner = token.strip().removeprefix("[").removesuffix("]").strip()
    if not inner:
        return []
    return [part.strip() for part in inner.split(",") if part.strip()]


def _grade_array_or_absent(ctx: dict, path: str, expected: str) -> None:
    """Grade an outline <expected> column of the form 'absent' | 'equal to [a, b]'
    against a success-path array field on the wire."""
    expected = expected.strip()
    if expected == "absent":
        wire_absent(ctx, path)
        return
    match = re.fullmatch(r"equal to (\[[^\]]*\])", expected)
    assert match, f"unrecognized array expected column: {expected!r}"
    want = _parse_bracket_list(match.group(1))
    actual = wire_field(ctx, path)
    assert actual == want, f"{path} expected {want!r}, got {actual!r}"


# ── Givens: declared-intent recorders (production has no config surface) ──


@given('"brand" is in supported_protocols')
def given_brand_in_supported_protocols(ctx: dict) -> None:
    """Declare the brand protocol. Production advertises only media_buy, so the
    brand top-level block is never emitted (#1592) — records intent."""
    _config(ctx).setdefault("supported_protocols", []).append("brand")


@given('"measurement" is in supported_protocols')
def given_measurement_in_supported_protocols(ctx: dict) -> None:
    """Declare the measurement protocol. Production advertises only media_buy, so
    the measurement block is never emitted (#1592) — records intent."""
    _config(ctx).setdefault("supported_protocols", []).append("measurement")


@given(
    "the tenant declares brand.rights=true right_types=[talent, music] "
    'available_uses=[likeness, sync] generation_providers=["openai"]'
)
def given_brand_posture(ctx: dict) -> None:
    """Declare a concrete brand posture (rights/right_types/available_uses/
    generation_providers). Records intent; the capabilities builder does not emit
    the brand block yet (#1592) so the value Thens xfail."""
    _config(ctx)["brand"] = {
        "rights": True,
        "right_types": ["talent", "music"],
        "available_uses": ["likeness", "sync"],
        "generation_providers": ["openai"],
    }


@given(parsers.parse("the tenant declares reporting delivery methods {methods} with offline protocols {protocols}"))
def given_reporting_delivery_methods(ctx: dict, methods: str, protocols: str) -> None:
    """Declare push-based reporting delivery methods + offline protocols. Records
    intent; production never emits media_buy.reporting_delivery_methods /
    offline_delivery_protocols (#1592)."""
    _config(ctx)["reporting_delivery_methods"] = None if methods.strip() == "omitted" else _parse_bracket_list(methods)
    _config(ctx)["offline_delivery_protocols"] = (
        None if protocols.strip() == "omitted" else _parse_bracket_list(protocols)
    )


@given(
    parsers.re(
        r"the tenant declares (?P<emission_state>(?:media_buy\.|wholesale_feed_webhooks\.).+|no mutating-webhook emission)$"
    )
)
def given_webhook_emission_state(ctx: dict, emission_state: str) -> None:
    """Declare a mutating-webhook emission posture (or its absence) for the
    webhook-signing required_when invariant. Records intent; production emits no
    webhook_signing block (#1592) so the must_equal_when invariant is ungraded."""
    _config(ctx)["webhook_emission_state"] = emission_state.strip()


@given(parsers.parse("the tenant declares {signing_posture} with identity block {identity_state}"))
def given_signing_posture_with_identity(ctx: dict, signing_posture: str, identity_state: str) -> None:
    """Declare a signing posture + identity-block state for the identity
    required_when invariant. Records intent; the builder never rejects
    signing-without-brand_json_url (identity/signing posture not built, #1592)."""
    _config(ctx)["signing_posture"] = signing_posture.strip()
    _config(ctx)["identity_state"] = identity_state.strip()


@given(parsers.parse('the tenant declares measurement.metrics with metric_id "{metric_id}"'))
def given_measurement_metric(ctx: dict, metric_id: str) -> None:
    """Declare one measurement metric by metric_id. Records intent; production
    emits no measurement block (#1592)."""
    _config(ctx).setdefault("measurement_metrics", []).append(metric_id)


# ── Thens: reporting_delivery_methods outline ────────────────────────────


@then(parsers.re(r"media_buy\.reporting_delivery_methods should be (?P<expected>absent|equal to \[[^\]]*\])$"))
def then_reporting_methods_value(ctx: dict, expected: str) -> None:
    """reporting_delivery_methods: absent (baseline polling only) or exactly the
    declared push methods (items ∈ {webhook, offline}, minItems 1, uniqueItems)."""
    _grade_array_or_absent(ctx, "media_buy.reporting_delivery_methods", expected)


@then(parsers.re(r"media_buy\.offline_delivery_protocols should be (?P<expected>absent|equal to \[[^\]]*\])$"))
def then_offline_protocols_value(ctx: dict, expected: str) -> None:
    """offline_delivery_protocols: absent unless reporting includes 'offline', then
    exactly the declared protocols (items ∈ cloud-storage-protocol enum)."""
    _grade_array_or_absent(ctx, "media_buy.offline_delivery_protocols", expected)
    value = wire_lookup(ctx, "media_buy.offline_delivery_protocols")
    if value is not WIRE_MISSING:
        invalid = set(value) - CLOUD_STORAGE_PROTOCOL_ENUM
        assert not invalid, f"offline_delivery_protocols carries non-enum values: {sorted(invalid)}"


@then(parsers.re(r"webhook_signing\.supported should be (?P<expected>.+)$"))
def then_webhook_signing_supported(ctx: dict, expected: str) -> None:
    """webhook_signing.supported conditional invariant (must_equal_when): when the
    seller advertises mutating-webhook emission it MUST equal true; when no trigger
    fires it may be true, false, or absent (honest tautology — no cross-field
    constraint). 'equal to true/false' grades the exact value; anything else is the
    no-trigger row (present→boolean or absent)."""
    expected = expected.strip()
    path = "webhook_signing.supported"
    if expected in ("equal to true", "equal to false"):
        actual = wire_field(ctx, path)
        assert actual is (expected == "equal to true"), f"{path} expected {expected}, got {actual!r}"
        return
    value = wire_lookup(ctx, path)
    if value is not WIRE_MISSING:
        assert isinstance(value, bool), f"{path} present but not a boolean: {value!r}"


# ── Thens: brand block ───────────────────────────────────────────────────


@then("the response should include brand section")
def then_brand_section_present(ctx: dict) -> None:
    """brand top-level block is present only when 'brand' is in supported_protocols.
    wire_dict pins present AND non-null AND a JSON object."""
    wire_dict(ctx, "brand")


@then(parsers.parse("brand.{field} should equal {expected}"))
def then_brand_field_equals(ctx: dict, field: str, expected: str) -> None:
    """Exact-echo a declared brand sub-field: rights (boolean), right_types /
    available_uses (arrays of right-type / right-use enum members),
    generation_providers (array of open strings)."""
    _assert_wire_equals(ctx, f"brand.{field}", expected)


# ── Thens: identity required_when verdict ────────────────────────────────


@then(parsers.parse("the seller capabilities builder should treat the configuration as {verdict}"))
def then_identity_signing_verdict(ctx: dict, verdict: str) -> None:
    """identity.brand_json_url required_when invariant: a seller declaring a signing
    posture with an absent/empty identity MUST be rejected (it cannot produce a
    conformant response), surfaced as a CONFIGURATION_ERROR (seller-side deployment
    fault, recovery terminal) naming brand_json_url. A no-posture config emits a
    valid success response (adcp + supported_protocols, no adcp_error)."""
    verdict = verdict.strip()
    if verdict.startswith("rejected"):
        from tests.helpers.envelope_assertions import assert_envelope_shape

        assert ctx.get("error") is not None, f"expected rejection, got a success response ({verdict!r})"
        assert_envelope_shape(
            ctx.get("wire_error_envelope"),
            "CONFIGURATION_ERROR",
            recovery="terminal",
            message_substr="brand_json_url",
        )
        return
    assert verdict == "a valid capabilities response", f"unrecognized verdict column: {verdict!r}"
    assert ctx.get("error") is None, f"expected a valid response, got error: {ctx.get('error')!r}"
    assert ctx.get("wire_error_envelope") is None, (
        f"expected a valid response, got a wire error envelope: {ctx.get('wire_error_envelope')!r}"
    )
    for path in ("adcp", "supported_protocols"):
        wire_field(ctx, path)


# ── Thens: measurement block ─────────────────────────────────────────────


@then("the response should include measurement section")
def then_measurement_section_present(ctx: dict) -> None:
    """measurement (x-status experimental) block present. wire_dict pins present
    AND non-null AND a JSON object."""
    wire_dict(ctx, "measurement")


@then("measurement.metrics should be a non-empty array")
def then_measurement_metrics_nonempty(ctx: dict) -> None:
    """metrics: minItems 1 (measurement requires at least one computed metric)."""
    metrics = wire_field(ctx, "measurement.metrics")
    assert isinstance(metrics, list) and metrics, f"measurement.metrics not a non-empty array: {metrics!r}"


@then(parsers.parse('each metrics entry\'s metric_id should match pattern "{pattern}" with length 1..64'))
def then_measurement_metric_id_shape(ctx: dict, pattern: str) -> None:
    """Every metrics[].metric_id is a vendor-metric-id: pattern ^[a-z][a-z0-9_]*$,
    minLength 1, maxLength 64 (core/vendor-metric-id.json)."""
    assert pattern == "^[a-z][a-z0-9_]*$", f"scenario pattern drifted from vendor-metric-id.json: {pattern!r}"
    metrics = wire_field(ctx, "measurement.metrics")
    for entry in metrics:
        metric_id = entry.get("metric_id")
        assert isinstance(metric_id, str) and _VENDOR_METRIC_ID_RE.match(metric_id), (
            f"metric_id does not match {pattern}: {metric_id!r}"
        )
        assert 1 <= len(metric_id) <= 64, f"metric_id length outside 1..64: {metric_id!r}"


@then(parsers.parse('a metrics entry should carry metric_id "{metric_id}"'))
def then_measurement_metric_present(ctx: dict, metric_id: str) -> None:
    """The declared metric_id round-trips: some metrics entry carries it exactly."""
    metrics = wire_field(ctx, "measurement.metrics")
    ids = [entry.get("metric_id") for entry in metrics]
    assert metric_id in ids, f"no metrics entry carries metric_id {metric_id!r}: {ids!r}"


@then(parsers.parse('experimental_features should contain "{feature}"'))
def then_experimental_features_contains(ctx: dict, feature: str) -> None:
    """Agents implementing measurement MUST list measurement.core in
    experimental_features (measurement block + supported_protocols descriptions)."""
    features = wire_field(ctx, "experimental_features")
    assert feature in features, f"experimental_features does not contain {feature!r}: {features!r}"
