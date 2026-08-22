"""MCP must not offer a rebuilt copy of an envelope it already captures.

``synthesized_error_envelope`` is what production WOULD emit for an exception,
recomputed by the harness from the same builder production uses. On IMPL that is
honest: there is no wire by definition, so the synthesized value is the only view
that exists and its name says so. On MCP there IS a wire, so the field is either
redundant (the wire is present) or a mask (the wire was lost) -- and a mask is
what let ``MediaBuyListEnv`` declare a wire it never captured, right up until
``salesagent-pldmk.24``.

``McpDispatcher``'s own comment already said "NEVER the synthesized fallback --
a dead MCP wire path must yield None here". The construction two lines below it
passed one anyway. These tests pin the comment.
"""

import json

import pytest
from fastmcp.exceptions import ToolError

from src.core.exceptions import AdCPValidationError, build_two_layer_error_envelope
from tests.harness.dispatchers import A2ADispatcher, ImplDispatcher, McpDispatcher, RestDispatcher


def _raising_env(exc: Exception):
    """A stand-in env whose every transport entry point raises *exc*."""

    class _Env:
        def call_impl(self, **kwargs):
            raise exc

        def call_mcp(self, **kwargs):
            raise exc

        def call_a2a(self, **kwargs):
            raise exc

        def call_rest(self, **kwargs):
            raise exc

        def build_rest_body(self, **kwargs):
            # Without this the REST leg never reaches the dispatcher's own error
            # arm -- the stub raises AttributeError first and the assertion holds
            # for a reason unrelated to what it claims to test.
            return {}

        def parse_rest_response(self, data):
            return data

    return _Env()


def _an_error() -> AdCPValidationError:
    return AdCPValidationError("boom", field="push_notification_config.authentication.credentials")


class TestMcpDoesNotSynthesize:
    def test_a_typed_error_with_no_captured_wire_yields_no_envelope_at_all(self):
        """A dead MCP wire path must produce nothing to read, not a rebuilt copy.

        This is the whole point: a test downstream that falls back to the
        synthesized value would go green off a value regenerated from the
        exception, which cannot witness a regression in the production
        translator -- both sides compute it from the same in-memory object.
        """
        result = McpDispatcher().dispatch(_raising_env(_an_error()))

        assert result.synthesized_error_envelope is None
        assert result.wire_error_envelope is None

    def test_a_tool_error_carrying_wire_json_is_read_as_the_wire(self):
        """The real capture path still works -- asserted with a REAL envelope.

        Without this case the sibling above is vacuous: a bare exception is
        neither a ToolError carrying JSON nor stash-carrying, so both capture
        paths return None by construction and the file would stay green with
        MCP's wire capture entirely dead. That is the exact defect pldmk.24
        fixed one commit ago, so it is the one this file must be able to see.
        """
        envelope = build_two_layer_error_envelope(_an_error())
        result = McpDispatcher().dispatch(_raising_env(ToolError(json.dumps(envelope))))

        assert result.wire_error_envelope == envelope
        assert result.synthesized_error_envelope is None

    def test_a_stashed_wire_envelope_is_read_as_the_wire(self):
        """The second capture path: an AdCPError carrying the harness stash."""
        exc = _an_error()
        envelope = build_two_layer_error_envelope(exc)
        exc._wire_error_envelope = envelope

        result = McpDispatcher().dispatch(_raising_env(exc))

        assert result.wire_error_envelope == envelope
        assert result.synthesized_error_envelope is None


class TestOnlyTheTransportWithNoWireMaySynthesize:
    """The contract ``TransportResult`` already documents, pinned as a whole.

    Pinning only the deleted construction would grade "line 229 stayed deleted".
    Pinning every dispatcher grades the rule that line violated, which is what
    stops the field quietly becoming a fallback again on some other transport.

    A2A passing here does NOT mean A2A is clean. It leaves this field ``None``
    while putting a builder-regenerated envelope into ``wire_error_envelope``
    instead -- the same substitution under the name of the real thing, which is
    strictly worse and is why it needs its own change (``salesagent-pldmk.26``).
    """

    def test_impl_still_synthesizes_because_it_has_no_wire_to_lose(self):
        """IMPL's value is load-bearing and must survive this change.

        Five integration tests read it. It is not a mask there: ``has_wire=False``
        is a definition for an in-process call, not a lost capture.
        """
        result = ImplDispatcher().dispatch(_raising_env(_an_error()))

        assert result.synthesized_error_envelope is not None
        assert result.wire_error_envelope is None

    @pytest.mark.parametrize("dispatcher", [A2ADispatcher, McpDispatcher, RestDispatcher])
    def test_a_transport_that_has_a_wire_never_synthesizes(self, dispatcher):
        result = dispatcher().dispatch(_raising_env(_an_error()))

        assert result.synthesized_error_envelope is None
