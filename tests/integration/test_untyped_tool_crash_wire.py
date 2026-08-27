"""A server bug must not be reported to the buyer as a downstream outage.

Five raise sites collapsed any untyped exception into ``AdCPAdapterError``, whose
code is ``SERVICE_UNAVAILABLE`` — a claim that a dependency is temporarily out and
that retrying will help. What actually reaches those arms is a genuine server bug:
an ``AttributeError``, a ``TypeError``, a ``KeyError`` in tool code. The identical
request will fail identically until someone ships a fix, so the retry the code
invites cannot work.

``INTERNAL_ERROR`` is what the server actually produced, and
``AdCPInternalError`` already says exactly that: "the request was well formed and
no dependency is down, but an invariant this seller relies on did not hold."

This is the same defect class as
``tests/integration/test_get_products_property_list_error_wire.py``, where a
resolver crash was reported as the buyer's ``VALIDATION_ERROR``. A fault on the
seller's side dressed as something the buyer can act on.

ONE parametrized test rather than one test per site (salesagent-45d27 acceptance
4): the sites differ only in which tool they live in, and 5 near-identical test
bodies would grade the copy-paste rather than the contract.

Graded on ``wire_error_envelope`` across every transport that has a wire, through
``assert_wire_error`` — the sanctioned surface. An ``_impl``-level
``pytest.raises`` cannot see the recovery hint, and the recovery is half of what
makes ``SERVICE_UNAVAILABLE`` a lie here: it is pinned ``transient``, which is the
retry invitation itself.

The sibling ``except AdCPError: raise`` arm at each site is deliberately NOT
exercised here — ``test_adapter_error_wire_classification.py`` already pins it,
and salesagent-rys3u.8 depends on it surviving.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.factories import PrincipalFactory, ProductFactory, PublisherPartnerFactory, TenantFactory
from tests.harness.transport import Transport

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

_WIRE_TRANSPORTS = [Transport.MCP, Transport.A2A, Transport.REST]

# The crash is a plain builtin on purpose. These arms exist to catch what nobody
# anticipated, so injecting a project exception would test the wrong thing.
_CRASH = AttributeError("'NoneType' object has no attribute 'get'")


@contextmanager
def _get_products_env():
    """A crash inside product conversion — src/core/tools/products.py."""
    from tests.harness.product import ProductEnv

    with ProductEnv() as env:
        tenant = TenantFactory(tenant_id="test_tenant")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        # A real product row: the crash lives inside the per-product conversion
        # loop, so an empty catalog would never reach it.
        ProductFactory(tenant=tenant, product_id="prod_crash")
        env.set_policy_approved()
        env.set_ranking_disabled()
        with patch(
            "src.core.tools.products.convert_product_model_to_schema",
            side_effect=_CRASH,
        ):
            yield env, {"brief": "video ads"}


@contextmanager
def _list_authorized_properties_env():
    """A crash inside the tool body — src/core/tools/properties.py."""
    from tests.harness.authorized_properties import AuthorizedPropertiesEnv

    with AuthorizedPropertiesEnv(tenant_id="crash-wire-properties", principal_id="test_principal") as env:
        tenant = TenantFactory(tenant_id="crash-wire-properties")
        PrincipalFactory(tenant=tenant, principal_id="test_principal")
        # A verified publisher: with none, the tool returns early and never
        # reaches the policy-parsing code the crash is injected into.
        PublisherPartnerFactory(tenant=tenant, publisher_domain="example.com")
        with patch(
            "src.core.tools.properties.safe_parse_json_field",
            side_effect=_CRASH,
        ):
            yield env, {}


@contextmanager
def _create_media_buy_env():
    """A crash inside the tool body — src/core/tools/media_buy_create.py."""
    from tests.harness.media_buy_create import MediaBuyCreateEnv

    now = datetime.now(UTC)
    with MediaBuyCreateEnv() as env:
        env.setup_media_buy_data()
        # The adapter FACTORY raising, not the adapter: a factory that blows up is
        # this seller's own bug, where an adapter call that fails is the downstream
        # outage SERVICE_UNAVAILABLE legitimately describes.
        env.mock["adapter"].side_effect = _CRASH
        yield (
            env,
            {
                "brand": {"domain": "crash-wire.example.com"},
                "start_time": (now + timedelta(days=1)).isoformat(),
                "end_time": (now + timedelta(days=8)).isoformat(),
                "packages": [
                    {
                        "product_id": "prod_1",
                        "budget": 5000.0,
                        "pricing_option_id": "cpm_usd_fixed",
                    }
                ],
                "idempotency_key": f"crash-wire-{uuid4().hex}",
            },
        )


_TOOLS = [
    pytest.param(_get_products_env, id="get_products"),
    pytest.param(_list_authorized_properties_env, id="list_authorized_properties"),
    pytest.param(_create_media_buy_env, id="create_media_buy"),
]


@pytest.mark.parametrize("transport", _WIRE_TRANSPORTS, ids=lambda t: t.value)
@pytest.mark.parametrize("tool_env", _TOOLS)
def test_untyped_crash_reaches_the_buyer_as_internal_error(integration_db, transport: Transport, tool_env: Any) -> None:
    """A builtin raised in tool code is reported as the seller's fault, not a retry."""
    with tool_env() as (env, call_kwargs):
        result = env.call_via(transport, **call_kwargs)

        assert result.is_error, (
            "an untyped crash in tool code must fail the request, got "
            f"{getattr(result, 'wire_response', None) or result.payload!r}"
        )
        # recovery is pinned explicitly rather than defaulted: SERVICE_UNAVAILABLE
        # and INTERNAL_ERROR would both satisfy a code-only assertion of "not the
        # buyer's fault", and the retry semantics are what actually differ.
        result.assert_wire_error("INTERNAL_ERROR", recovery="transient")
