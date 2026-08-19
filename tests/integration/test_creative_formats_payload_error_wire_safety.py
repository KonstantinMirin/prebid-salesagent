"""An unreachable creative agent must not leak its raw failure text into the
SUCCESS payload's ``errors[]``.

The sibling obligation to ``tests/integration/test_typed_error_wire_safety.py``,
on the OTHER buyer-facing error carrier. ``list_creative_formats`` degrades
gracefully: one unreachable agent does not fail the request, it produces an
``AGENT_UNREACHABLE`` entry in ``errors[]`` on an otherwise successful response
(``src/core/creative_agent_registry.py`` ``list_all_formats_with_errors``).
Because the response is a success, ``result.is_error`` is False and
``wire_error_envelope`` is ``None`` — the two-layer envelope helpers cannot
grade this path at all, which is why it needs its own assertion surface
(``assert_no_marker_in_payload_errors``).

The carrier is in scope for the same MUST NOT list as the envelope:

* AdCP 3.1.1 ``dist/docs/3.1.1/building/operating/transport-errors.mdx``
  § Security Considerations / Seller Requirements (lines 659-670) opens with
  "Error responses flow through LLM context. Every field is client-facing" and
  forbids internal service names/hostnames/IP addresses and upstream API
  responses.
* ``dist/compliance/3.1.1/universal/error-compliance.yaml`` (:323) grades a
  typed error code "via either ``adcp_error`` (envelope) or ``errors[]``
  (payload)" — the two carriers have equal status. That step validates the
  CODE only, so the message-content obligation asserted here is ungraded by the
  storyboard and rests on the normative prose above.

The construction site fixed here interpolated BOTH the caught exception and the
seller-configured ``agent.agent_url``::

    message=f"Creative agent at {agent.agent_url} is unreachable: {e}"

Both are dropped. The raw cause is still captured server-side by the existing
``logger.error(..., exc_info=True)`` one line above it — ``adcp.types.Error`` is
an SDK model, so it has no ``internal_detail`` slot to route it through.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.creative_agent_registry import CREATIVE_AGENT_UNREACHABLE_MESSAGE, CreativeAgentRegistry
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.creative_formats import CreativeFormatsEnv
from tests.harness.transport import Transport
from tests.helpers.envelope_assertions import assert_no_marker_in_payload_errors

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Seller-internal infrastructure detail of the shape a real transport failure
# carries. Same fake-DSN marker technique as
# tests/bdd/steps/domain/security_wire_safety.py: if it shows up in errors[],
# the raw third-party text reached the buyer.
_SECRET_MARKER = "creative-agent.internal.svc.cluster.local:8443"
_RAW_FAILURE_TEXT = f"[Errno -2] Name or service not known: {_SECRET_MARKER}"

# The seller-configured agent endpoint. The buyer never sent it and this seller
# does not publish creative-agent URLs through its capability declarations, so
# transport-errors.mdx:666 ("MUST NOT include: internal service names,
# hostnames, or IP addresses") keeps it off the wire too.
_AGENT_URL = "https://creative-agent.internal.svc.cluster.local:8443/mcp"

# IMPL has no wire body; the three wire transports all serialize the same
# success payload, and the message is baked in before any of them runs.
_TRANSPORTS = [Transport.A2A, Transport.MCP, Transport.REST]


@pytest.mark.parametrize("transport", _TRANSPORTS, ids=lambda t: t.value)
def test_unreachable_agent_yields_a_safe_payload_error(integration_db, transport, monkeypatch):
    """errors[0] names the failure in first-party terms and carries no raw text."""
    # ADCP_TESTING short-circuits list_all_formats_with_errors to the checked-in
    # reference catalog, which never reaches the failure arm under test.
    monkeypatch.setenv("ADCP_TESTING", "false")

    with CreativeFormatsEnv(tenant_id="fmt-wire-safety", principal_id="fmt-wire-principal") as env:
        tenant = TenantFactory(tenant_id="fmt-wire-safety", subdomain="fmt-wire-safety")
        PrincipalFactory(tenant=tenant, principal_id="fmt-wire-principal")

        agent = MagicMock()
        agent.agent_url = _AGENT_URL
        agent.name = "Internal Creative Agent"

        # Run the REAL aggregation method (the construction site under test)
        # instead of the harness stub; only the per-agent fetch is faulted.
        real_registry = CreativeAgentRegistry()
        with (
            patch.object(CreativeAgentRegistry, "_get_tenant_agents", return_value=[agent]),
            patch.object(CreativeAgentRegistry, "_build_adcp_client", return_value=MagicMock()),
            patch.object(
                CreativeAgentRegistry,
                "_fetch_formats_from_agent",
                new=AsyncMock(side_effect=ConnectionError(_RAW_FAILURE_TEXT)),
            ),
        ):
            env.mock["registry"].return_value.list_all_formats_with_errors = real_registry.list_all_formats_with_errors
            result = env.call_via(transport)

        assert not result.is_error, f"an unreachable agent must degrade, not fail the request: {result.payload!r}"

        errors = (result.wire_response or {}).get("errors")
        assert errors, (
            f"a failed agent must be reported in the success payload's errors[], got {result.wire_response!r}"
        )

        # POSITIVE: the exact first-party sentence the seller publishes, at the
        # protocol position. Mandatory — a negative-only check passes vacuously.
        assert errors[0]["code"] == "AGENT_UNREACHABLE", f"errors[0].code={errors[0]['code']!r}"
        assert errors[0]["message"] == CREATIVE_AGENT_UNREACHABLE_MESSAGE, (
            f"errors[0].message={errors[0]['message']!r}, expected the first-party sentence "
            f"{CREATIVE_AGENT_UNREACHABLE_MESSAGE!r}"
        )

        # NEGATIVE: neither the third party's text nor the seller-configured
        # endpoint appears anywhere in errors[].
        assert_no_marker_in_payload_errors(result.wire_response, _SECRET_MARKER)
        assert_no_marker_in_payload_errors(result.wire_response, _RAW_FAILURE_TEXT)
