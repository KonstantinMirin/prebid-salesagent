"""Domain steps for the local egress/SSRF refusal feature.

Grades the buyer-visible half of AdCP 3.1.1 L1 § "Webhook URL validation
(SSRF)" through ``property_list.agent_url`` on ``get_products`` — the one
counterparty-supplied URL that every wire transport (including REST, since
911cf5259) can carry, which is what makes the same scenario runnable on
a2a / mcp / rest / e2e_rest.

The refusal itself is produced by production: the harness routes @egress
scenarios to ``RealResolverProductEnv``, which leaves ``resolve_property_list``
unpatched so the request reaches the real resolver and the real egress seam.

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

    Asserted identically for every Examples row, which IS spec point 6's second
    half: an unresolvable host and a blocked reserved address must be
    indistinguishable on the wire, or the refusal is a name-existence oracle.
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
