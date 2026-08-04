"""Domain steps for the local egress/SSRF refusal feature.

Grades the buyer-visible half of AdCP 3.1.1 L1 § "Webhook URL validation
(SSRF)" through two buyer-supplied URLs: ``property_list.agent_url`` on
``get_products`` (fetch-now — the refusal happens at send time) and
``push_notification_config.url`` on ``create_media_buy`` (store-now/dial-later
— the refusal happens at ingest, the only moment a request exists to carry
it). Both run on every wire transport, which is what makes the same scenario
runnable on a2a / mcp / rest / e2e_rest.

The refusal itself is produced by production: the harness routes @egress
scenarios to ``RealResolverProductEnv`` (real resolver, real seam) and
@egress_create scenarios to ``MediaBuyCreateEnv`` (real ``_impl``, real
ingest verdict via ``reject_unsafe_webhook_registration_url`` in
``src.core.webhook_validator``).

Note the ingest verdict is NOT the seam's: the registration gate is
deliberately DNS-free, so an unresolvable-but-public hostname is ACCEPTED at
ingest and only re-checked when the callback is dialled. The seam
(``src.core.security.outbound_http``) remains the send-time gate. Scenarios
that expect an ingest refusal must therefore pick a cause the DNS-free gate
actually rejects — a reserved-address literal — not an unresolvable name; and,
to keep the non-disclosure obligation gradable, one the gate does not report by
naming the blocked hostname or a dotted-quad range (see the Examples rationale
in the feature). The two gates also differ on the wire: the seam surfaces as
INVALID_REQUEST, the registration gate as VALIDATION_ERROR (it raises
``AdCPValidationError``), both correctable and both naming the field.

Steps store in ctx (on top of what ``dispatch_request`` stores):
    ctx["supplied_agent_url"] — the URL the buyer sent, so the non-disclosure
        Then can assert its absence structurally rather than by eyeball.
"""

from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import urlparse

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps._outcome_helpers import _require, assert_wire_rejection
from tests.bdd.steps.generic._dispatch import dispatch_request

# The list_id is irrelevant to a refusal — the seam refuses before a connection
# is opened, so the path is never built. Fixed so the request is well-formed.
_LIST_ID = "test_list"

# Anything that could spell an IP address. Deliberately over-broad: the tokens it
# yields are then handed to ``ipaddress``, which is the actual decision. A regex
# alone would either miss ``fd00:ec2::254`` or flag every ISO timestamp.
_ADDRESS_CANDIDATE_RE = re.compile(r"[0-9A-Fa-f:.]{3,}")


def _wire_error_envelope(ctx: dict) -> dict:
    """Return the wire error envelope, failing loudly if the request did not fail."""
    envelope = ctx.get("wire_error_envelope")
    assert isinstance(envelope, dict), (
        "Expected a wire error envelope — the request was supposed to be refused. "
        f"Got {envelope!r}; recorded error={ctx.get('error')!r}, response={ctx.get('response')!r}"
    )
    return envelope


def _ip_addresses_in(text: str) -> list[str]:
    """Every substring of *text* that really is an IP address.

    ``ipaddress.ip_address`` is the oracle rather than a pattern: it accepts
    ``169.254.169.254`` and ``fd00:ec2::254`` and rejects ``3.1.1`` and the
    ``12:34:56`` of a timestamp, so the assertion cannot be defeated by a leak in
    a form the pattern did not anticipate, nor go red on innocent text.
    """
    found: list[str] = []
    for token in _ADDRESS_CANDIDATE_RE.findall(text):
        try:
            found.append(str(ipaddress.ip_address(token.strip(".:"))))
        except ValueError:
            continue
    return found


# ── Given steps ─────────────────────────────────────────────────────


@given("both outbound egress escape hatches are open")
def given_egress_hatches_open(ctx: dict) -> None:
    """Run this scenario with ADCP_OUTBOUND_ALLOW_PRIVATE and ..._ALLOW_INSECURE on.

    The permissive posture is the DELIBERATE choice for a refusal that must mean
    the same thing everywhere: with both hatches open the reserved-range gate and
    the scheme gate are disarmed, so a refusal can only come from the two causes
    that are immune to them — a blocked cloud-metadata address, and a host that
    does not resolve. That is also the posture the e2e stack runs in, so the
    in-process transports and e2e_rest grade one production, not three.
    """
    ctx["env"].set_egress_hatches(private=True, insecure=True)


@given("both outbound egress escape hatches are closed")
def given_egress_hatches_closed(ctx: dict) -> None:
    """Run this scenario with both escape hatches explicitly off — the production posture.

    Pinned rather than assumed: ``run_all_tests_host.sh`` exports both as ``true``
    for the full host run, so a scheme-refusal scenario that leaves them unset
    passes under ``saci`` and fails only in the full run. Over e2e_rest the env
    declares this unrealizable (the server's environment is not ours to set).
    """
    ctx["env"].set_egress_hatches(private=False, insecure=False)


# ── When steps ──────────────────────────────────────────────────────


@when(parsers.parse('the buyer requests products with a property list agent at "{agent_url}"'))
def when_request_products_with_property_list(ctx: dict, agent_url: str) -> None:
    """Dispatch get_products carrying a buyer-supplied property_list.agent_url."""
    ctx["supplied_agent_url"] = agent_url
    dispatch_request(
        ctx,
        brief="egress refusal test",
        property_list={"agent_url": agent_url, "list_id": _LIST_ID},
    )


@when(parsers.parse('the buyer syncs a creative whose format agent is at "{agent_url}"'))
def when_sync_creative_with_agent_url(ctx: dict, agent_url: str) -> None:
    """Dispatch sync_creatives carrying a buyer-supplied creatives[].format_id.agent_url.

    The third buyer-supplied URL on the protocol surface. Unlike the two above,
    this one is a PER-CREATIVE field, so the refusal has to name which creative
    — hence the indexed ``field`` the Then step asserts.

    The creative is built through ``CreativeAssetFactory`` (overriding only
    ``format_id``) rather than as a literal dict: a payload missing a required
    field is rejected by the MCP wrapper's typed parameters BEFORE any egress
    decision, and that VALIDATION_ERROR resembles a refusal closely enough to
    pass a careless assertion for entirely the wrong reason.
    """
    from adcp.types import FormatId

    from tests.factories.creative_asset import CreativeAssetFactory

    ctx["supplied_agent_url"] = agent_url
    creative = CreativeAssetFactory(
        creative_id="c_egress_refusal",
        name="Egress Refusal Creative",
        format_id=FormatId(id="display_300x250_image", agent_url=agent_url),
    )
    dispatch_request(ctx, creatives=[creative])


@when(parsers.parse('the buyer creates a media buy with push notification url "{webhook_url}"'))
def when_create_media_buy_with_push_url(ctx: dict, webhook_url: str) -> None:
    """Dispatch create_media_buy carrying a buyer-supplied push_notification_config.url.

    The ingest twin of the get_products dispatch above: the URL is stored now
    and dialled later, so the refusal under test must happen on THIS request.
    Runs on the media-buy create harness (@egress_create routes there); the
    request body is otherwise the harness's minimal valid create.
    """
    from tests.bdd.steps.generic.given_media_buy import harness_create_request_kwargs

    ctx["supplied_agent_url"] = webhook_url
    kwargs = harness_create_request_kwargs(ctx)
    kwargs["push_notification_config"] = {"url": webhook_url}
    dispatch_request(ctx, **kwargs)


# ── Then steps ──────────────────────────────────────────────────────


@then(parsers.parse('the request is rejected with INVALID_REQUEST naming field "{field}"'))
def then_rejected_invalid_request_field(ctx: dict, field: str) -> None:
    """Assert the wire envelope is INVALID_REQUEST / correctable and names the field.

    ``correctable`` is the load-bearing half: before the seam migration this
    surfaced as SERVICE_UNAVAILABLE / transient, which tells the buyer to retry a
    request that will be refused identically forever. ``field`` is the other
    half — with a message that must disclose nothing, it is the only channel that
    can say WHICH of the request's URLs to fix.
    """
    assert_wire_rejection(ctx, "INVALID_REQUEST", recovery="correctable", field=field)


@then(parsers.parse('the refusal message on both envelope layers is exactly "{message}"'))
def then_refusal_message_is_exactly(ctx: dict, message: str) -> None:
    """Assert BOTH envelope layers carry exactly *message* — no more, no less.

    The expected text is a Gherkin literal on purpose, never imported from
    production: importing it would make any message change agree with itself, and
    a regression to ``f"{_BLOCKED_MESSAGE} (host {h})"`` would still satisfy a
    substring check. Equality on both layers is what makes such a regression red.

    Both the SEND-time scenarios and the INGEST scenario now pass one literal
    for every Examples row: an unresolvable host and a blocked reserved
    address must be indistinguishable on the wire, or the refusal is a
    name-existence oracle — spec point 6's second half. The registration gate
    used to vary its ``<reason>`` per cause (which CIDR, which resolved
    address); that was the disclosure bug this scenario now pins closed, via
    ``url_validator._RESTRICTED_RANGE_MESSAGE``. Non-disclosure of the
    buyer's OWN supplied host/address is still carried by
    :func:`then_envelope_discloses_nothing`, not by sameness — the two Thens
    check different things.
    """
    envelope = _wire_error_envelope(ctx)
    assert envelope["errors"][0]["message"] == message, (
        f"errors[0].message={envelope['errors'][0]['message']!r}, expected exactly {message!r}"
    )
    assert envelope["adcp_error"]["message"] == message, (
        f"adcp_error.message={envelope['adcp_error']['message']!r}, expected exactly {message!r}"
    )


@then("the error envelope names neither the supplied host nor any IP address")
def then_envelope_discloses_nothing(ctx: dict) -> None:
    """Assert the WHOLE serialized envelope leaks neither the host nor an address.

    Over the whole envelope, not just ``errors[0].message``: ``context``,
    ``details``, ``suggestion`` and the envelope-level summary are all
    buyer-visible, and a leak in any of them turns ``property_list.agent_url``
    into an internal host-and-port scanner with a spec-compliant envelope wrapped
    around it (AdCP 3.1.1 L1 point 6).
    """
    envelope = _wire_error_envelope(ctx)
    serialized = json.dumps(envelope, default=str)

    host = urlparse(str(_require(ctx, "supplied_agent_url"))).hostname
    assert host is not None, f"malformed supplied_agent_url in ctx: {ctx.get('supplied_agent_url')!r}"
    assert host not in serialized, f"refusal echoed the supplied host {host!r} back to the buyer: {serialized}"

    leaked = _ip_addresses_in(serialized)
    assert leaked == [], f"refusal disclosed IP address(es) {leaked} to the buyer: {serialized}"


@then(parsers.parse('the creative is rejected with INVALID_REQUEST naming field "{field}"'))
def then_creative_rejected_per_item(ctx: dict, field: str) -> None:
    """Assert the PER-ITEM failure carries the seam's own classification.

    Per-item rather than request-level because ``format_id.agent_url`` is a
    per-CREATIVE field: the pinned sync-creatives-response schema calls a
    synchronous success "best-effort processing with per-item status/failures"
    and says ``action="failed"`` items are "per-item validation/processing
    failures, not operation-level failures". The sibling
    ``push_notification_config.url`` fails the whole request because THAT field
    is request-level; the analogy does not carry to this one.

    ``field`` is the load-bearing half. The refusal message says nothing about
    the destination (L1 point 6), so it is the only channel that can tell a
    buyer WHICH of up to 100 creatives to fix.
    """
    response = _require(ctx, "response")
    creatives = response["creatives"] if isinstance(response, dict) else response.creatives
    assert creatives, f"expected a per-creative result, got {response!r}"
    entry = creatives[0]
    action = entry["action"] if isinstance(entry, dict) else getattr(entry.action, "value", entry.action)
    assert str(action) == "failed", f"a creative whose agent_url egress refused must not sync; action={action!r}"

    errors = entry["errors"] if isinstance(entry, dict) else entry.errors
    assert errors, f"a failed creative must carry an error; got {entry!r}"
    error = errors[0]
    code = error["code"] if isinstance(error, dict) else error.code
    recovery = error["recovery"] if isinstance(error, dict) else error.recovery
    got_field = error["field"] if isinstance(error, dict) else error.field
    assert code == "INVALID_REQUEST", f"errors[0].code={code!r} — a buyer-supplied URL is buyer-correctable"
    assert recovery == "correctable", f"errors[0].recovery={recovery!r}"
    assert got_field == field, f"errors[0].field={got_field!r}, expected {field!r}"
