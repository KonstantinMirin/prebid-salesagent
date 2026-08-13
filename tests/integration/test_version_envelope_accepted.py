"""MCP tools must accept the AdCP 3.1 version envelope (GH #1512).

AdCP 3.1.1 composes ``core/version-envelope.json`` via ``allOf`` into EVERY
request and response schema — "so the version semantics live in exactly one
place", per the schema's own description. Its two fields are ``adcp_version``
(release-precision, e.g. ``"3.1"``) and ``adcp_major_version``. The conformance
runner therefore sends them on every call, injected at a single chokepoint
(``@adcp/sdk@11.0.0`` ``dist/lib/protocols/index.js::applyVersionEnvelope``,
citing spec PR ``adcontextprotocol/adcp#3493``).

Our MCP tools declare neither field. FastMCP validates tool arguments with
pydantic BEFORE our code runs, and pydantic's message for an undeclared keyword
is literally "Unexpected keyword argument" — which is exactly what the
2026-08-12 in-network Storyboard Conformance run reports, 31 times:

    mcp/security_transport/signed_requests/get_capabilities (error)
    — VALIDATION_ERROR: Unexpected keyword argument

The blast radius is larger than the error count suggests, because one of the 31
IS capability discovery. When the probe fails, the runner never populates
``profile.raw_capabilities``, so the ``request_signer`` gate in ``checkRequires``
no-ops (it is written to no-op when capabilities are unreadable) and the
``signed_requests`` storyboard is GRADED instead of skipped — 40 ledgered
failures the spec says we do not owe (salesagent-g6m2.3).

A2A is unaffected: it reads parameters out of a dict and tolerates unknown keys.
That asymmetry is why 80 of the 81 ledger entries are ``mcp::``.

Graded by these 3.1.1 storyboard steps, among others:
``universal/capability-discovery.yaml`` (get_capabilities,
get_capabilities_filtered), ``universal/version-negotiation.yaml``
(get_capabilities_with_version), ``universal/signed-requests.yaml``
(get_capabilities).
"""

from __future__ import annotations

import pytest

from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.capabilities import CapabilitiesEnv
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The envelope exactly as the SDK puts it on the wire. `adcp_version` is
# release-precision (VERSION.RELEASE) per core/version-envelope.json's pattern
# `^\d+\.\d+(-[a-zA-Z0-9.-]+)?$` — NOT the full semver pin.
VERSION_ENVELOPE = {"adcp_version": "3.1", "adcp_major_version": 3}


@pytest.fixture
def capabilities_env(integration_db):
    with CapabilitiesEnv(tenant_id="version-envelope", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="version-envelope")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        yield env


def test_mcp_capability_probe_accepts_the_version_envelope(capabilities_env):
    """The reproduction: the discovery probe the whole gate depends on.

    This is the call the conformance runner makes first. If it errors, every
    capability-gated storyboard silently loses its gate.
    """
    result = capabilities_env.call_via(Transport.MCP, **VERSION_ENVELOPE)

    assert result.is_success, (
        f"get_adcp_capabilities rejected the AdCP 3.1 version envelope: {result.wire_error_envelope or result.error}"
    )


def test_a2a_capability_probe_accepts_the_version_envelope(capabilities_env):
    """A2A is the control: it already tolerates the envelope.

    Pins the asymmetry the ledger shows (80 of 81 failures are mcp::) so a fix
    that "solves" MCP by breaking A2A cannot pass.
    """
    result = capabilities_env.call_via(Transport.A2A, **VERSION_ENVELOPE)

    assert result.is_success, (
        "A2A rejected the version envelope — it accepted it before this change: "
        f"{result.wire_error_envelope or result.error}"
    )


def test_request_envelope_is_not_echoed_back_into_the_response(capabilities_env):
    """Accepting the envelope must not mean echoing it back.

    The response model DOES carry `adcp_version` / `adcp_major_version` — 3.1.1
    composes `core/version-envelope.json` into every response schema too, where
    the semantics differ: on a response the field means "the release the seller
    actually served", not "what the buyer asked for". Reflecting the request's
    values would therefore be a false claim about what we served.

    We do not populate the response envelope at all today. That is a real gap
    against the same clause, and it is deliberately out of scope here (this bug
    is request REJECTION) — but pinning it means the gap has to be closed by a
    decision rather than by accident.
    """
    result = capabilities_env.call_via(Transport.MCP, **VERSION_ENVELOPE)

    assert result.is_success
    payload = result.payload
    assert payload.adcp is not None, "the response's own adcp block must still be populated"
    assert payload.adcp_version is None, "the request's adcp_version was echoed back as if served"
    assert payload.adcp_major_version is None, "the request's adcp_major_version was echoed back"


def test_unknown_arguments_are_still_rejected(capabilities_env):
    """The fix must accept the SPEC'd envelope, not everything.

    A `**kwargs`-shaped fix would make every typo a silent no-op and would also
    defeat `universal/schema-validation.yaml`, which grades unknown-field
    handling. Only the two envelope fields are newly acceptable.
    """
    result = capabilities_env.call_via(Transport.MCP, definitely_not_a_real_adcp_field="x")

    assert result.is_error, "an undeclared, non-envelope argument must still be rejected"
