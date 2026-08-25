"""Regression tests for issue #1237: sync_creatives account raw-dict crash.

_handle_sync_creatives_skill passed `account` as a raw dict to core, but
resolve_account calls .root on it expecting an AccountReference RootModel.
Verifies the A2A handler wraps the dict in AccountReference before forwarding.
"""

from unittest.mock import MagicMock, patch

import pytest
from adcp.types import AccountReference as LibraryAccountReference

from src.core.exceptions import AdCPValidationError
from src.core.resolved_identity import ResolvedIdentity
from src.core.schema_helpers import to_account_reference

_MOCK_IDENTITY = ResolvedIdentity(
    principal_id="principal_123",
    tenant_id="tenant_123",
    tenant={"tenant_id": "tenant_123"},
    protocol="a2a",
)


def test_to_account_reference_handles_supported_inputs():
    """The shared helper validates dicts and preserves typed/empty values."""
    account_dict = {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
    result = to_account_reference(account_dict)
    assert isinstance(result, LibraryAccountReference)
    assert result.root.brand.domain == "example.com"
    assert result.root.operator == "op-1"
    assert result.root.sandbox is False
    assert to_account_reference(result) is result
    assert to_account_reference(None) is None


def test_to_account_reference_rejects_invalid_account_payload():
    """Malformed oneOf account payloads fail as a TYPED error at the shared helper.

    Updated for #1417: the to_* coercions carry an internal
    ``adcp_validation_boundary`` (the coerce_creative_filters pattern), so the
    rejection is an ``AdCPValidationError`` with a top-level suggestion — the
    previous raw ``pydantic.ValidationError`` leak WAS the disease this test
    now guards against.
    """
    with pytest.raises(AdCPValidationError) as excinfo:
        to_account_reference({})


class TestSyncCreativesAccountCoercion:
    """A2A handler must coerce raw account dict to AccountReference before calling core."""

    def _call_handler_with_account(self, account_param):
        """Invoke _handle_sync_creatives_skill with a given account parameter value."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler.__new__(AdCPRequestHandler)

        captured = {}

        def _fake_core(creatives, **kwargs):
            captured["account"] = kwargs.get("account")
            result = MagicMock()
            result.model_dump.return_value = {}
            return result

        with patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool", side_effect=_fake_core):
            import asyncio

            asyncio.run(
                handler._handle_sync_creatives_skill(
                    parameters={"creatives": [], "account": account_param},
                    identity=_MOCK_IDENTITY,
                )
            )

        return captured.get("account")

    def test_dict_account_is_wrapped_in_account_reference(self):
        """A raw dict account is coerced to AccountReference with field values preserved."""
        account_dict = {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        result = self._call_handler_with_account(account_dict)
        assert isinstance(result, LibraryAccountReference)
        assert result.root.brand.domain == "example.com"
        assert result.root.operator == "op-1"
        assert result.root.sandbox is False

    def test_none_account_passes_through_as_none(self):
        """None account is passed through unchanged."""
        result = self._call_handler_with_account(None)
        assert result is None

    def test_already_typed_account_passes_through(self):
        """An already-validated AccountReference is forwarded by identity, not re-validated."""
        typed = LibraryAccountReference.model_validate(
            {"brand": {"domain": "example.com"}, "operator": "op-1", "sandbox": False}
        )
        result = self._call_handler_with_account(typed)
        assert result is typed


class TestSyncCreativesFormatIdStaysWire:
    """The A2A handler must forward format_id as a WIRE DICT, never as a model.

    salesagent-kyc89: the handler upgraded each creative's format_id with
    ``upgrade_legacy_format_id``, which returns OUR ``FormatId`` subclass. Pydantic
    does not re-validate a model instance that already satisfies an annotation, so
    that subclass survived into ``CreativeAsset.format_id`` -- making A2A the only
    transport whose request carried a different CLASS. Pydantic v2 equality is
    class-sensitive, so the registry match in ``_processing`` found nothing and
    every generative creative was silently written as a plain static asset.

    The upgrade itself must stay (the library CreativeAsset rejects both a bare
    string and a dict with no agent_url), so what is graded here is its SHAPE: a
    JSON-native dict, identical to the request MCP and REST build.
    """

    @staticmethod
    def _forwarded_creatives(creatives: list[dict]) -> list:
        """The ``creatives`` argument the handler hands to the core tool."""
        from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

        handler = AdCPRequestHandler.__new__(AdCPRequestHandler)
        captured = {}

        def _fake_core(creatives, **kwargs):
            captured["creatives"] = creatives
            result = MagicMock()
            result.model_dump.return_value = {}
            return result

        with patch("src.a2a_server.adcp_a2a_server.core_sync_creatives_tool", side_effect=_fake_core):
            import asyncio

            asyncio.run(
                handler._handle_sync_creatives_skill(
                    parameters={"creatives": creatives},
                    identity=_MOCK_IDENTITY,
                )
            )

        return captured["creatives"]

    def test_structured_format_id_is_forwarded_as_a_dict(self):
        """A structured format_id reaches core as a dict, not a FormatId instance."""
        forwarded = self._forwarded_creatives(
            [
                {
                    "creative_id": "c1",
                    "name": "Structured",
                    "format_id": {"agent_url": "https://creative.example.com", "id": "display_300x250"},
                    "assets": {},
                }
            ]
        )
        format_id = forwarded[0]["format_id"]
        assert format_id == {"agent_url": "https://creative.example.com/", "id": "display_300x250"}

    def test_legacy_string_format_id_is_upgraded_but_stays_a_dict(self):
        """A legacy string still gains its agent_url -- as a dict the library accepts."""
        forwarded = self._forwarded_creatives(
            [{"creative_id": "c1", "name": "Legacy", "format_id": "display_300x250", "assets": {}}]
        )
        format_id = forwarded[0]["format_id"]
        assert format_id == {
            "agent_url": "https://creative.adcontextprotocol.org/",
            "id": "display_300x250",
        }

    def test_parameterized_format_id_keeps_its_parameters(self):
        """AdCP 2.5 width/height survive the dump rather than being dropped."""
        forwarded = self._forwarded_creatives(
            [
                {
                    "creative_id": "c1",
                    "name": "Parameterized",
                    "format_id": {
                        "agent_url": "https://creative.example.com",
                        "id": "display",
                        "width": 300,
                        "height": 250,
                    },
                    "assets": {},
                }
            ]
        )
        assert forwarded[0]["format_id"] == {
            "agent_url": "https://creative.example.com/",
            "id": "display",
            "width": 300,
            "height": 250,
        }

    def test_forwarded_creative_builds_the_same_class_every_transport_builds(self):
        """The end the divergence actually had: CreativeAsset.format_id's CLASS.

        Building the library CreativeAsset from what A2A forwards must produce the
        same concrete format_id type as building it from the untouched wire dict --
        which is exactly what MCP and REST do.
        """
        from adcp.types import CreativeAsset

        wire = {
            "creative_id": "c1",
            "name": "Same class",
            "format_id": {"agent_url": "https://creative.example.com", "id": "display_300x250"},
            "assets": {},
        }
        forwarded = self._forwarded_creatives([dict(wire)])[0]

        from_a2a = CreativeAsset(**forwarded)
        from_other_transports = CreativeAsset(**wire)

        assert type(from_a2a.format_id) is type(from_other_transports.format_id)
        assert from_a2a.format_id == from_other_transports.format_id
