"""Raw third-party exception text must not be baked into a TYPED ``AdCPError``
at the raise site, where it reaches the buyer-facing wire.

Distinct from the untyped-exception obligation (commit d00707a7f, graded by
``tests/integration/test_prkv8_untyped_exception_wire_leak.py``). That fix
closed the *untyped* fallthrough in ``normalize_to_adcp_error()`` — the shared
A2A/MCP/REST chokepoint — so an arbitrary ``Exception``'s ``str()`` no longer
becomes the buyer-facing message. It cannot touch this case: the exception
raised here is ALREADY an ``AdCPError``, so ``normalize_to_adcp_error()`` passes
it through verbatim. For a typed error THE RAISE SITE IS THE WIRE — the text is
interpolated upstream of every sanitisation point.

The site under test is ``src/core/property_list_resolver.py``'s
``httpx.RequestError`` arm, which used to read::

    except httpx.RequestError as exc:
        raise AdCPAdapterError(f"Failed to connect to property list service: {url} — {exc}") from exc

and now passes ``exc`` as the non-wire ``internal_detail=`` instead.

``resolve_property_list`` is called directly from ``_get_products_impl``
(``src/core/tools/products.py:425``) with **no** surrounding try/except — that
is deliberate and documented at the call site — so the typed error propagates
straight to the transport boundary and its message becomes the buyer's
``errors[0].message``. ``httpx.RequestError``'s text is produced by httpx /
the underlying transport and routinely carries seller-internal infrastructure
detail: resolver failures, proxy host:port, connection targets.

AdCP 3.1.1 ``dist/docs/3.1.1/building/operating/transport-errors.mdx``
§ Security Considerations / Seller Requirements (lines 659-670) is a MUST-NOT
list covering exactly this: hostnames, upstream responses, and internal
infrastructure detail must never reach the buyer. The conformance storyboard
(``dist/compliance/3.1.1/universal/error-compliance.yaml``) grades only the
error CODE for a generic error, so this obligation is ungraded there and rests
on the normative prose.

Sibling exemplar: ``tests/integration/test_prkv8_untyped_exception_wire_leak.py``.
Success-payload sibling:
``tests/integration/test_creative_formats_payload_error_wire_safety.py``.
"""

from unittest.mock import patch

import httpx
import pytest

# Captured at import time, BEFORE ProductEnv patches the module attribute.
# ProductEnv stubs ``resolve_property_list`` as an "external service", but the
# leak lives INSIDE that function, so the stub is redirected back to the real
# production callable below and only the HTTP boundary (httpx) is mocked.
from src.core.property_list_resolver import resolve_property_list as real_resolve_property_list
from tests.factories import PrincipalFactory, TenantFactory
from tests.harness.product import ProductEnv
from tests.harness.transport import Transport
from tests.helpers.envelope_assertions import assert_envelope_shape, assert_no_marker_in_envelope

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# A plainly-internal infrastructure detail of the shape a real httpx
# RequestError carries (resolver/proxy target). If it appears anywhere in the
# wire envelope, the raw third-party exception text leaked to the buyer.
_SECRET_MARKER = "proxy.internal.svc.cluster.local:3128"
_RAW_HTTPX_TEXT = f"[Errno -2] Name or service not known: {_SECRET_MARKER}"

# IP literal, not a hostname: ``_validate_agent_url`` -> ``check_url_ssrf``
# short-circuits on IP literals, so the reproduction needs no DNS at all.
# 93.184.216.34 is public (not loopback/link-local/private), so it passes SSRF.
_AGENT_URL = "https://93.184.216.34/"

# REST is excluded on purpose: ``ProductEnv.build_rest_body`` forwards only
# (brief, brand, filters, adcp_version), so ``property_list`` never reaches the
# REST route and the site cannot be driven over that transport from this env.
# The leak is transport-independent — it is baked into the message before any
# boundary runs — so A2A + MCP grade it.
_TRANSPORTS = [Transport.A2A, Transport.MCP]


@pytest.mark.parametrize("transport", _TRANSPORTS, ids=lambda t: t.value)
class TestTypedAdCPErrorDoesNotLeakRawExceptionText:
    """A typed ``AdCPError`` raised around a third-party failure must not put
    that third party's raw text on the buyer-facing wire, on any transport."""

    def test_raw_httpx_text_absent_from_wire_envelope(self, integration_db, transport):
        with ProductEnv(tenant_id="typed-leak", principal_id="typed-leak-principal") as env:
            tenant = TenantFactory(tenant_id="typed-leak", subdomain="typed-leak")
            PrincipalFactory(tenant=tenant, principal_id="typed-leak-principal")

            # Run the REAL resolver (the raise site under test) instead of the
            # harness stub; only the outbound HTTP call is mocked.
            env.mock["resolve_property_list"].side_effect = real_resolve_property_list

            with patch.object(
                httpx.AsyncClient,
                "get",
                side_effect=httpx.ConnectError(_RAW_HTTPX_TEXT),
            ):
                result = env.call_via(
                    transport,
                    brief="video ads",
                    property_list={"agent_url": _AGENT_URL, "list_id": "buyer-list-1"},
                )

            assert result.is_error, f"expected an error result on {transport.value}, got {result.payload!r}"

            # Primary authority: the wire envelope itself (tests/CLAUDE.md
            # "Error Verification Policy" — the harness's exception
            # reconstruction is lossy). AdCPAdapterError -> SERVICE_UNAVAILABLE,
            # recovery transient.
            # POSITIVE half: the buyer still gets the seller's own first-party
            # sentence naming what failed — the fix replaces the provenance of
            # the message, it does not blank it.
            assert_envelope_shape(
                result.wire_error_envelope,
                "SERVICE_UNAVAILABLE",
                recovery="transient",
                message_substr="Failed to connect to property list service",
            )

            # NEGATIVE half — the obligation: the third party's raw text must not
            # be anywhere in the envelope (message, details, suggestion, context).
            assert_no_marker_in_envelope(result.wire_error_envelope, _SECRET_MARKER)
            assert_no_marker_in_envelope(result.wire_error_envelope, _RAW_HTTPX_TEXT)
