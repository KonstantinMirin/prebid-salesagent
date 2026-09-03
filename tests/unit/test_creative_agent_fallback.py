"""Unit tests for the creative agent's MCP tool-result parser.

The fallback classes that used to live here (``TestStructuredContentFallbackTrigger``,
``TestSchemaValidationFailureTriggersFallback``) tested a mechanism that no
longer exists: the adcp SDK's own strict Pydantic parsing of
``list_creative_formats`` responses, which sometimes rejected a TextContent-only
reply and triggered a fallback to the raw-MCP path. The SDK client
(``ADCPMultiAgentClient``) has been removed from the OPERATOR agent path
entirely — it is routed through the guarded MCP seam instead — so there is no SDK-side
strict parser left to reject anything, and therefore nothing left to trigger a
fallback FROM. ``_parse_mcp_tool_result``'s own tolerant, per-format validation
(covered below) is now the ONLY ingestion path, for both the operator method
and the counterparty raw-MCP method.

Two things follow for the assertions here, and both are graded rather than
assumed. First, no refusal is matched by its authored sentence any more:
``AdCPSalesAgentError.message`` is a read-only CODE_TABLE property, so
``pytest.raises(..., match=...)`` would only ever re-assert the code's own table
entry. The authored text is a NON-WIRE diagnostic and is graded on
``internal_detail``, with the buyer-facing string graded for what it must NOT
carry (AdCP 3.1.1 transport-errors.mdx § Security Considerations: upstream
responses and seller endpoints stay off the wire). Second, the seam returns a
closed ``OutboundResult`` — no ``httpx.Response``, no ``.response`` attribute —
so these tests hand production the real type instead of a mock, which is the
only way the content-type branches under test actually execute.
"""

import json
import logging

import pytest

from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry
from src.core.exceptions import AdCPValidationError
from src.core.security.egress.response import OutboundResult
from src.core.security.outbound_http import CounterpartyUrl


@pytest.fixture
def registry():
    return CreativeAgentRegistry()


SAMPLE_FORMATS_JSON = '{"formats": [{"format_id": {"agent_url": "https://creative.example.com", "id": "display_image"}, "name": "Display Image", "type": "display"}]}'

_NO_TEXT_CONTENT_DETAIL = "No text content in MCP tool result"


def _outbound(body: str, *, content_type: str) -> OutboundResult:
    """The seam's OWN return type, built for real rather than mocked.

    ``asend`` returns a closed :class:`OutboundResult`; a stand-in carrying an
    ``httpx.Response`` under ``.response`` is a shape production never produces,
    and every read of ``result.headers`` / ``.json()`` / ``.text`` would land on
    an auto-created attribute — the content-type branch under test would never
    run and the assertion would pass vacuously.
    """
    return OutboundResult(
        http_status=200,
        headers={"content-type": content_type},
        content=body.encode(),
        attempts=1,
        duration_seconds=0.0,
    )


def _stub_seam(monkeypatch, result: OutboundResult) -> list[dict]:
    """Point the registry's ``asend`` at ``result``; return the recorded calls.

    Each entry is the complete call — the url positional plus every keyword — so
    a case asserts the whole thing at once instead of reading arguments back off
    a mock after the fact.
    """
    calls: list[dict] = []

    async def fake_asend(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return result

    monkeypatch.setattr("src.core.creative_agent_registry.asend", fake_asend)
    return calls


def _assert_detail_stayed_off_the_wire(exc: AdCPValidationError, detail: str) -> None:
    """The authored sentence is a server-side diagnostic, never buyer-facing text.

    ``message`` is read-only and comes from CODE_TABLE, so the authored half has
    exactly one legitimate destination (``internal_detail``) and one forbidden
    one (``str(exc)``, i.e. the wire message). Graded as a pair: asserting only
    that the detail is carried says nothing about whether it also leaked.
    """
    assert exc.internal_detail == detail
    assert detail not in str(exc), f"the authored diagnostic reached the buyer-facing message: {exc!s}"


class TestParseMcpToolResult:
    """Test the MCP tool result parser."""

    def test_parses_text_content(self, registry):
        """Content with text type → parsed formats."""
        result = {"content": [{"type": "text", "text": SAMPLE_FORMATS_JSON}]}
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].name == "Display Image"

    def test_no_text_content_raises(self, registry):
        """Content with no text items → raises AdCPValidationError.

        A silent ``return []`` used to mask failures as 'no formats'.
        """
        result = {"content": [{"type": "image", "data": "..."}]}
        with pytest.raises(AdCPValidationError) as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger())
        # The agent_url came from the BUYER (this helper is only reached on the
        # counterparty branch), so an unusable answer is their correctable input —
        # not a seller misconfiguration, and not a transient outage.
        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.recovery == "correctable"
        _assert_detail_stayed_off_the_wire(excinfo.value, _NO_TEXT_CONTENT_DETAIL)

    async def test_the_fetch_threads_field_down_to_the_refusal(self, registry, monkeypatch):
        """``_fetch_formats_raw_mcp`` passes its ``field`` into the parse step.

        The helper-level test below proves the raise CARRIES a field it is given;
        this proves the caller actually GIVES it one. Both halves are needed: the
        threading lives at two call sites inside the fetch, and deleting it leaves
        every other test green because no other caller passes a field.
        """
        buyer_field = "creatives[0].format_id.agent_url"
        # A well-formed JSON-RPC envelope whose result carries no text content —
        # the condition the parse step refuses on.
        calls = _stub_seam(
            monkeypatch,
            _outbound(
                json.dumps({"result": {"content": [{"type": "image", "data": "..."}]}}),
                content_type="application/json",
            ),
        )

        agent = CreativeAgent(agent_url="https://buyer-agent.test", name="buyer-agent")
        with pytest.raises(AdCPValidationError) as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=buyer_field))

        assert len(calls) == 1, f"the seam owns retry; the fetch dialled {len(calls)} times"
        assert calls[0]["provenance"] == CounterpartyUrl(field=buyer_field), "the seam call lost the buyer field"
        assert excinfo.value.field == buyer_field, (
            "the refusal reached the buyer without naming which input to fix — the fetch "
            "dropped the field on its way to the parse step"
        )
        _assert_detail_stayed_off_the_wire(excinfo.value, _NO_TEXT_CONTENT_DETAIL)

    async def test_a_response_with_no_result_is_a_correctable_buyer_error(self, registry, monkeypatch):
        """A JSON body carrying no ``result`` refuses as VALIDATION_ERROR / correctable.

        This is the fetch's OWN raise, distinct from the parse step's: the agent
        answered, but with nothing that is a tools/call result at all. It is graded
        separately because mutating both raises together lets the parse step's
        grader mask this one — the mistake round 1 of test-verify made.

        The agent_url is the BUYER's (this method is only reached on the
        counterparty branch), so the refusal is their correctable input, not a
        seller misconfiguration and not a transient outage.
        """
        buyer_field = "creatives[0].format_id.agent_url"
        _stub_seam(
            monkeypatch,
            _outbound(json.dumps({"jsonrpc": "2.0", "id": 1}), content_type="application/json"),  # no "result"
        )

        agent = CreativeAgent(agent_url="https://buyer-agent.test", name="buyer-agent")
        with pytest.raises(AdCPValidationError) as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=buyer_field))

        exc = excinfo.value
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.recovery == "correctable"
        assert exc.field == buyer_field
        # The endpoint is a server-side diagnostic. ``field`` is what the buyer
        # needs; the address rides the non-wire channel only (AdCP 3.1.1
        # transport-errors.mdx § Security Considerations).
        _assert_detail_stayed_off_the_wire(exc, f"No parseable result in MCP response from {agent.agent_url}")

    async def test_the_sse_branch_threads_field_into_the_parse_step(self, registry, monkeypatch):
        """The SSE path threads ``field`` at its OWN call site.

        The fetch has two content-type branches and each calls the parse step
        separately, so grading only the JSON one leaves the SSE threading free to
        rot. This body therefore carries a real ``result`` — reaching the parse
        step through SSE — whose content has no text, which is what that step
        refuses on. (A body with no ``result`` would stop at the fetch's own raise
        and never exercise the threading at all.)
        """
        buyer_field = "creatives[3].format_id.agent_url"
        _stub_seam(
            monkeypatch,
            _outbound(
                'data: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "image"}]}}\n',
                content_type="text/event-stream",
            ),
        )

        agent = CreativeAgent(agent_url="https://buyer-agent.test", name="buyer-agent")
        with pytest.raises(AdCPValidationError) as excinfo:
            await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl(field=buyer_field))

        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.field == buyer_field, "the SSE branch dropped the buyer field on its way to the parse step"
        _assert_detail_stayed_off_the_wire(excinfo.value, _NO_TEXT_CONTENT_DETAIL)

    async def test_auth_headers_forwarded(self, registry, monkeypatch):
        """The agent's credentials ride the seam call, under its configured header name.

        Kept from the pre-seam suite because the behaviour it grades survived the
        migration intact: the fetch still builds the auth header itself and hands
        it to ``asend``. Only the transport it is handed to changed, so the mock
        moved to the seam rather than the assertion being dropped.
        """
        calls = _stub_seam(
            monkeypatch,
            _outbound(
                json.dumps({"result": {"content": [{"type": "text", "text": '{"formats": []}'}]}}),
                content_type="application/json",
            ),
        )

        agent = CreativeAgent(
            agent_url="https://buyer-agent.test",
            name="buyer-agent",
            auth={"type": "token", "credentials": "test-token"},
            auth_header="x-test-auth",
        )
        formats = await registry._fetch_formats_raw_mcp(agent, provenance=CounterpartyUrl())

        assert formats == []
        assert len(calls) == 1
        assert calls[0]["url"] == "https://buyer-agent.test/mcp", (
            "the tools/call went somewhere other than the MCP endpoint"
        )
        assert calls[0]["headers"]["x-test-auth"] == "test-token"
        assert calls[0]["json"]["params"]["name"] == "list_creative_formats"

    def test_field_names_the_buyer_input_when_the_caller_has_one(self, registry):
        """A refusal carries the ``field`` that says WHICH buyer input to fix.

        The only production caller reaches here on the counterparty branch, where
        it holds the buyer's ``creatives[].format_id.agent_url`` path. A sync
        request carries up to 100 creatives, so without ``field`` the buyer is
        told their input is correctable but not which one — the same channel
        lanes 2 and 3 established as the only non-disclosing way to say it.

        Graded directly because every current caller happens to pass ``None``:
        dropping the threading would otherwise be invisible.
        """
        result = {"content": [{"type": "image", "data": "..."}]}
        with pytest.raises(AdCPValidationError) as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger(), field="creatives[0].format_id.agent_url")

        assert excinfo.value.field == "creatives[0].format_id.agent_url"

    def test_empty_content_raises(self, registry):
        """Empty content list → raises AdCPValidationError.

        A silent ``return []`` used to mask failures as 'no formats'.
        """
        result = {"content": []}
        with pytest.raises(AdCPValidationError) as excinfo:
            registry._parse_mcp_tool_result(result, logging.getLogger())
        assert excinfo.value.error_code == "VALIDATION_ERROR"
        assert excinfo.value.recovery == "correctable"
        _assert_detail_stayed_off_the_wire(excinfo.value, _NO_TEXT_CONTENT_DETAIL)


def _mcp_text_result(payload: dict) -> dict:
    """Wrap a list_creative_formats payload as an MCP tools/call TextContent result."""
    import json

    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


# Two fully-known formats the pinned adcp library understands completely.
_KNOWN_FORMAT_A = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_300x250_image"},
    "name": "Medium Rectangle",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
_KNOWN_FORMAT_B = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "display_728x90_image"},
    "name": "Leaderboard",
    "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
}
# AdCP-additive asset_type the canonical reference agent serves but the pinned
# (and latest) adcp closed Literal union does NOT model. This is the exact
# production defect class.
_ADDITIVE_FORMAT = {
    "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "tracking_pixel"},
    "name": "Tracking Pixel",
    "assets": [{"item_type": "individual", "asset_id": "pixel", "asset_type": "pixel_tracker", "required": True}],
}


class TestTolerantPerFormatIngestion:
    """Hermetic regression (Postel / asymmetric strictness).

    One unknown AdCP-additive asset_type must NOT nuke the whole
    list_creative_formats response. Fully-understood formats are returned;
    formats whose ONLY problem is an unrecognized additive asset_type are
    passed through (the unknown additive asset_type is tolerated) with ONE
    aggregated WARNING; genuinely malformed formats still fail LOUD.
    """

    def test_unknown_additive_asset_type_passes_through(self, registry, caplog):
        """Mixed batch: 2 known + 1 additive(pixel_tracker) → all 3 returned.

        SDK 5.7 accepts unknown asset_types as UnknownFormatAsset instead of
        rejecting them. This is better Postel's law behavior — unknown types
        are preserved, not dropped.
        """
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _ADDITIVE_FORMAT, _KNOWN_FORMAT_B]})

        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())

        ids = sorted(f.format_id.id for f in formats)
        assert ids == [
            "display_300x250_image",
            "display_728x90_image",
            "tracking_pixel",
        ], "All formats including additive-asset_type should pass through"

    def test_all_known_formats_pass_through_unchanged(self, registry):
        """No additive types → all formats returned, zero warnings (no behavior change)."""
        import logging

        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, _KNOWN_FORMAT_B]})
        formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert sorted(f.format_id.id for f in formats) == ["display_300x250_image", "display_728x90_image"]

    def test_genuinely_malformed_format_still_fails_loud(self, registry):
        """A real schema bug (not an additive enum) must NOT be masked — fail loud."""
        import logging

        malformed = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken"},
            "name": 12345,  # wrong type — a genuine contract violation, not additive growth
            "assets": [{"item_type": "individual", "asset_id": "primary", "asset_type": "image", "required": True}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, malformed]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_additive_type_with_structurally_broken_asset_fails_loud(self, registry):
        """Unknown asset_type AND a structurally broken asset → not purely additive → fail loud."""
        import logging

        broken_additive = {
            "format_id": {"agent_url": "https://creative.adcontextprotocol.org", "id": "broken_pixel"},
            "name": "Broken Pixel",
            # asset_type unknown AND asset_id/required missing — substituting a known
            # asset_type would STILL fail, so this is not benign additive growth.
            "assets": [{"item_type": "individual", "asset_type": "pixel_tracker"}],
        }
        result = _mcp_text_result({"formats": [_KNOWN_FORMAT_A, broken_additive]})
        with pytest.raises(Exception, match="(?i)valid"):
            registry._parse_mcp_tool_result(result, logging.getLogger())

    def test_all_formats_additive_passes_through(self, registry, caplog):
        """SDK 5.7 accepts additive-only batch via UnknownFormatAsset — returns the format."""
        import logging

        result = _mcp_text_result({"formats": [_ADDITIVE_FORMAT]})
        with caplog.at_level(logging.WARNING):
            formats = registry._parse_mcp_tool_result(result, logging.getLogger())
        assert len(formats) == 1
        assert formats[0].format_id.id == "tracking_pixel"
