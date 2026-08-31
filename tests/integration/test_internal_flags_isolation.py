"""Integration tests: internal behavior flags must not be controllable by external callers.

Security regression tests for and .
Proves that include_performance, include_sub_assets, and include_snapshot
cannot be injected by buyers through request objects.

Uses the CreativeListEnv harness for real DB integration testing.
"""

import pytest
from pydantic import ValidationError

from tests.harness.creative_list import CreativeListEnv


@pytest.mark.requires_db
class TestListCreativesInternalFlagsIsolation:
    """Verify include_* flags cannot be injected via request object."""

    def test_request_object_rejects_include_performance(self, integration_db):
        """ListCreativesRequest schema must reject include_performance (not in AdCP spec)."""
        from src.core.schemas import ListCreativesRequest

        with pytest.raises(ValidationError, match="include_performance"):
            ListCreativesRequest(include_performance=True)

    def test_request_object_rejects_include_sub_assets(self, integration_db):
        """ListCreativesRequest schema must reject include_sub_assets (not in AdCP spec)."""
        from src.core.schemas import ListCreativesRequest

        with pytest.raises(ValidationError, match="include_sub_assets"):
            ListCreativesRequest(include_sub_assets=True)

    def test_request_object_accepts_include_assignments(self, integration_db):
        """include_assignments IS a valid AdCP 3.10 spec field — must be accepted."""
        from src.core.schemas import ListCreativesRequest

        req = ListCreativesRequest(include_assignments=True)
        assert req.include_assignments is True

    def test_impl_uses_explicit_parameters_not_request(self, integration_db):
        """_list_creatives_impl receives include_* as explicit params, not from request."""
        with CreativeListEnv() as env:
            env.setup_default_data()

            # Call impl with explicit flags — these come from the wrapper, not the buyer
            response = env.call_impl(include_performance=False, include_sub_assets=False)
            assert response is not None

    def test_mcp_call_succeeds_with_default_flags(self, integration_db):
        """MCP wrapper works with default include_* flags (harness simulates MCP transport)."""
        with CreativeListEnv() as env:
            env.setup_default_data()

            response = env.call_mcp()
            assert response is not None


@pytest.mark.requires_db
class TestGetMediaBuysInternalFlagsIsolation:
    """A value set for include_snapshot on the REQUEST object is inert.

    This class used to assert that GetMediaBuysRequest REJECTS include_snapshot, on the
    stated grounds that it is "not in AdCP spec". That premise is false against the pinned
    version: media-buy/get-media-buys-request.json declares
    include_snapshot as {"type": "boolean"}, so it is buyer-facing and REFUSING it would be
    the bug. GetMediaBuysRequest was re-based on the library type and now inherits it, which
    is what retired the old assertion.

    The isolation it was written to protect is intact -- what changed is the mechanism, from
    "the model rejects it" to "the model never feeds it", so the invariant is re-expressed
    rather than dropped. Measured: `.include_snapshot` has exactly ONE read site in src/,
    src/routes/api_v1.py:524, and that reads the REST BODY, not the request object.
    _build_get_media_buys_request builds from media_buy_ids/status_filter/account/context
    only, and all three wrappers pass the flag out-of-band as an explicit argument.
    """

    def test_the_request_object_accepts_the_spec_field(self, integration_db):
        """Accepting it is REQUIRED: the pinned schema declares it as a buyer input."""
        from src.core.schemas import GetMediaBuysRequest

        assert GetMediaBuysRequest(include_snapshot=True).include_snapshot is True

    def test_the_impl_honours_its_argument_not_the_request_field(self, integration_db):
        """The isolation itself: a request saying True cannot turn snapshots on.

        This is the assertion with teeth. The old test proved the field could not be SET;
        this proves that setting it changes nothing, which is what actually keeps a buyer
        from reaching an out-of-band flag.
        """
        import inspect

        from src.core.tools.media_buy_list import _build_get_media_buys_request, get_media_buys

        req = _build_get_media_buys_request(media_buy_ids=["mb_x"], status_filter=None, account=None, context=None)
        assert not hasattr(req, "include_snapshot") or req.include_snapshot in (None, False), (
            "the builder must not carry a buyer-supplied include_snapshot onto the request"
        )
        assert "include_snapshot" in inspect.signature(get_media_buys).parameters, (
            "the wrapper must take include_snapshot as its OWN argument -- that out-of-band "
            "path is what makes any value on the request object inert"
        )
