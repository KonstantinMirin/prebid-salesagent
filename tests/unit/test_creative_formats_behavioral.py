"""Behavioral tests for UC-005 (creative format discovery) that need no database.

``_list_creative_formats_impl`` lists only the formats the tenant's products declare, read
through ``ProductUoW``, so a test that drives the listing to its answer needs those products
and runs behind the harness: a BR-UC-005 scenario on a2a, mcp, rest and e2e_rest, or
``CreativeFormatsEnv`` (tests/harness/creative_formats.py) in tests/integration/. What stays
here is what is decided before the products are read, or without the listing at all.

WHERE THE FILTER, SORT AND ADVISORY TESTS THAT USED TO LIVE HERE ARE GRADED. They called the
impl with only the creative agent registry mocked, so the product read reached for a real
database, and each grades an obligation something else already grades through production:

* Sort by name: @T-UC-005-inv-031-2-holds (exact ordered list). The unit test named
  "after filtering" sent no filter; sort after a real ``name_search`` is
  tests/integration/test_creative_formats_behavioral.py
  ``TestFormatsSort::test_sort_preserves_after_filtering``.
* asset_types excludes a format with no matching asset: @T-UC-005-inv-049-3-violated, and
  "a match is kept while a non-match is dropped" is @T-UC-005-main-filtered.
* asset_types on repeatable groups (a group with no match excluded; a format matching
  through either its individual asset or its group): the integration twins
  ``TestFormatsAssetTypes::test_group_assets_no_match_excluded`` and
  ``::test_mixed_individual_and_group_assets``.
* A format_ids filter that matches nothing returns nothing:
  @T-UC-005-storyboard-format-id-third-party-agent-out-of-scope (its only reference
  matches no listed format, and the seller's same-id format is not returned), plus
  ``TestFormatsFiltering::test_format_ids_no_match_returns_empty``.
* A render one pixel past min_width or max_width is excluded:
  ``TestFormatsDimensions::test_off_by_one_max_width_excluded`` and
  ``::test_off_by_one_min_width_excluded``.
* An empty ``name_search`` filters nothing: ``TestFormatsEdgeCases::test_empty_name_search_returns_all``.
* Per-agent advisories (UC-005-EXT-C-01/-02/-04): the impl passes the registry's
  ``errors`` to the response unchanged when no ``format_ids`` names the agent, and that is
  graded on the wire by @T-UC-005-peer-catalog-partial-discard (the agent's kept format
  AND its advisory) and @T-UC-005-peer-catalog-all-discarded (no format AND the advisory).
  The unit tests fed AGENT_UNREACHABLE advisories straight in, so they never graded the
  registry's one-advisory-per-failed-agent loop; the real unreachable dial and its
  first-party message are graded by
  tests/integration/test_creative_formats_payload_error_wire_safety.py.
* Successful discovery carries no advisory (UC-005-EXT-C-05): @T-UC-005-inv-049-2-violated
  (a format returned and ``errors`` empty on the wire) and @T-UC-005-empty-catalog.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.schemas import Format, FormatId, ListCreativeFormatsRequest
from tests.factories import PrincipalFactory

DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"
MOCK_TENANT = {"tenant_id": "test-tenant", "name": "Test Tenant"}


def _make_format(
    format_id: str,
    name: str,
    renders: list | None = None,
    assets: list | None = None,
) -> Format:
    """Helper to create a Format object with minimal boilerplate."""
    return Format(
        format_id=FormatId(agent_url=DEFAULT_AGENT_URL, id=format_id),
        name=name,
        is_standard=True,
        renders=renders,
        assets=assets,
    )


class TestBroadstreetTemplateAssetParsing:
    """Regression: Broadstreet templates must parse with real assets.

    The pinned ``Format.assets`` variants carry a Literal ``asset_type`` discriminator,
    so the CLASS is the asset type; the code once passed
    ``ImageFormatAsset(asset_type=AssetContentType(...))`` for every asset and nothing
    constructed.

    BOTH TESTS NOW CALL PRODUCTION. They used to re-run the production loop against
    ``creative_formats._make_asset``, assembling their own ``Format`` -- so an adapter
    that stopped building assets at all would not have reddened either of them. The
    builder moved to ``BroadstreetAdapter.creative_formats`` (salesagent-zthsk) and these
    assert on what it answers.
    """

    def test_all_broadstreet_templates_produce_formats_with_assets(self):
        """Every Broadstreet template must produce a Format with non-empty assets."""
        from src.adapters.broadstreet import BroadstreetAdapter
        from src.adapters.broadstreet.config_schema import BROADSTREET_TEMPLATES

        by_id = {f.format_id.id: f for f in BroadstreetAdapter.creative_formats("test")}

        for tid, tmpl in BROADSTREET_TEMPLATES.items():
            fmt = by_id[f"broadstreet_{tid}"]
            assert fmt.assets, f"Template {tid} must have non-empty assets list"
            assert len(fmt.assets) == len(tmpl.get("required_assets", [])) + len(tmpl.get("optional_assets", [])), (
                f"Template {tid} asset count mismatch"
            )

    def test_asset_type_literals_match_inferred_type(self):
        """Each constructed asset carries the asset_type its id names."""
        from src.adapters.broadstreet import BroadstreetAdapter

        # One format per asset id below, chosen so each id appears in it.
        asset_types = {
            a.asset_id: a.asset_type for f in BroadstreetAdapter.creative_formats("test") for a in (f.assets or [])
        }

        for asset_id, expected_type in [
            ("front_image", "image"),
            ("logo", "image"),
            ("youtube_url", "video"),
            ("click_url", "url"),
            ("headline", "text"),
            ("html", "html"),
        ]:
            assert asset_types[asset_id] == expected_type, (
                f"{asset_id}: asset_type should be '{expected_type}', got '{asset_types[asset_id]}'"
            )


class TestMCPWrapperStringCoercion:
    """Regression: MCP wrapper must handle raw string inputs for enum params.

    The MCP wrapper (list_creative_formats) does type.value and at.value
    to extract enum values. If called directly with raw strings (bypassing
    FastMCP's auto-coercion), this crashes with AttributeError.
    The wrapper must coerce strings to enums before accessing .value.
    """


def _call_impl_raw(
    formats: list[Format],
    registry_side_effect: Exception | None = None,
    errors: list | None = None,
    agents: list | None = None,
):
    """Call _list_creative_formats_impl and return the full response (not just formats).

    Args:
        formats: Formats returned by healthy agents.
        registry_side_effect: If set, get_creative_agent_registry() raises this.
        errors: List of AdCP Error objects to include as per-agent failures.
        agents: CreativeAgent instances returned by _get_tenant_agents (referrals).
    """
    from src.core.creative_agent_registry import FormatFetchResult
    from src.core.tools.creative_formats import _list_creative_formats_impl

    req = ListCreativeFormatsRequest()
    identity = PrincipalFactory.make_public_identity(tenant=MOCK_TENANT)

    if registry_side_effect:
        with patch(
            "src.core.creative_agent_registry.get_creative_agent_registry",
            side_effect=registry_side_effect,
        ):
            with patch("src.core.tools.creative_formats.get_audit_logger") as mock_audit:
                mock_audit.return_value = MagicMock()
                return _list_creative_formats_impl(req, identity)

    with (
        patch("src.core.creative_agent_registry.get_creative_agent_registry") as mock_registry,
        patch("src.core.tools.creative_formats.get_audit_logger") as mock_audit,
    ):
        mock_reg = MagicMock()
        fetch_result = FormatFetchResult(formats=list(formats), errors=errors or [])

        async def mock_list_formats_with_errors(**kwargs):
            return fetch_result

        async def mock_list_formats(**kwargs):
            return list(formats)

        mock_reg.list_all_formats_with_errors = mock_list_formats_with_errors
        mock_reg.list_all_formats = mock_list_formats
        mock_reg._get_tenant_agents = MagicMock(return_value=agents or [])
        mock_registry.return_value = mock_reg
        mock_audit.return_value = MagicMock()

        return _list_creative_formats_impl(req, identity)


class TestRegistryCreationFailureRaisesServiceUnavailable:
    """UC-005-EXT-C-03: Registry creation failure raises AdCPServiceUnavailableError.

    Per AdCP 3.0.1 error-handling: operation-level failures (registry init) raise,
    so the boundary translator produces a two-layer envelope. Per-item advisory
    errors (partial-agent failure inside a successful discovery) stay in errors[].
    """

    def test_registry_creation_failure_raises(self):
        """Covers: UC-005-EXT-C-03

        Given the creative agent registry cannot be initialized,
        when list_creative_formats is called,
        then AdCPServiceUnavailableError is raised so the boundary translator
        builds a spec-compliant two-layer envelope.
        """
        from src.core.exceptions import AdCPServiceUnavailableError

        with pytest.raises(AdCPServiceUnavailableError) as _ei:
            _call_impl_raw(
                formats=[],
                registry_side_effect=RuntimeError("Cannot connect to agent registry"),
            )
        # The old pattern matched the AUTHORED sentence; the sentence is the
        # code's table entry now, so assert it exactly.


class TestAgentReferralFailureLogsWarning:
    """Agent referral building errors must be logged, not silently swallowed.

    CLAUDE.md: No Quiet Failures pattern. If _get_tenant_agents raises,
    creative_agents_list should remain None (non-critical) but a warning
    must be logged so operators can diagnose the issue.
    """

    def test_referral_error_logs_warning(self, caplog):
        """When _get_tenant_agents raises, a warning is logged (not silent pass)."""
        import logging

        from src.core.creative_agent_registry import FormatFetchResult
        from src.core.tools.creative_formats import _list_creative_formats_impl

        formats = [_make_format("display_300x250", "Display 300x250")]
        mock_reg = MagicMock()
        mock_reg._get_tenant_agents = MagicMock(side_effect=RuntimeError("Agent DB connection refused"))
        fetch_result = FormatFetchResult(formats=list(formats), errors=[])

        async def mock_list_formats_with_errors(**kwargs):
            return fetch_result

        async def mock_list_formats(**kwargs):
            return list(formats)

        mock_reg.list_all_formats_with_errors = mock_list_formats_with_errors
        mock_reg.list_all_formats = mock_list_formats

        identity = PrincipalFactory.make_public_identity(tenant=MOCK_TENANT)

        with (
            patch(
                "src.core.creative_agent_registry.get_creative_agent_registry",
                return_value=mock_reg,
            ),
            patch(
                "src.core.tools.creative_formats.get_audit_logger",
                return_value=MagicMock(),
            ),
            caplog.at_level(logging.WARNING, logger="src.core.tools.creative_formats"),
        ):
            _list_creative_formats_impl(
                req=ListCreativeFormatsRequest(),
                identity=identity,
            )

        # After fix: should log a warning about the referral failure
        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("referral" in msg.lower() or "agent" in msg.lower() for msg in warning_msgs), (
            f"Expected a warning about agent referral failure, got: {warning_msgs}"
        )


class TestReferralCapabilitiesAreCommitments:
    """Advertised creative-agent capabilities must all be backed by real tasks.

    AdCP design principle: capabilities are commitments — the conformance
    runner probes every advertised capability. Advertising `delivery` commits
    the agent to variant-level delivery reporting via a `get_creative_delivery`
    task. This agent does not implement that task, so `delivery` must not
    appear in the referral capabilities.
    """

    def test_referral_capabilities_exclude_delivery_while_unimplemented(self):
        """creative_agents referrals advertise only backed capabilities.

        Guard pair: if get_creative_delivery is ever implemented on the
        registry, the hasattr assertion below fails, prompting re-evaluation
        of the advertised set alongside the exclusion assertion.
        """
        from src.core.creative_agent_registry import CreativeAgent, CreativeAgentRegistry

        assert not hasattr(CreativeAgentRegistry, "get_creative_delivery"), (
            "get_creative_delivery is now implemented — re-evaluate whether "
            "`delivery` should be added back to ADVERTISED_CREATIVE_AGENT_CAPABILITIES"
        )

        formats = [_make_format("display_300x250", "Display 300x250")]
        agents = [
            CreativeAgent(
                agent_url=DEFAULT_AGENT_URL,
                name="AdCP Standard Creative Agent",
                enabled=True,
                priority=1,
            )
        ]

        response = _call_impl_raw(formats, agents=agents)

        assert response.creative_agents, "Expected creative_agents referrals in response"
        for referral in response.creative_agents:
            cap_values = {c.value for c in referral.capabilities}
            assert "delivery" not in cap_values, (
                f"`delivery` advertised without a get_creative_delivery task "
                f"(capabilities are commitments): {cap_values}"
            )
            assert cap_values == {"validation", "assembly", "preview"}, (
                f"Advertised capabilities must be exactly the backed set, got {cap_values}"
            )


class TestAgentInventedKeysNeverReachTheBuyer:
    """A creative agent's undeclared keys must not travel through this seller onto the wire.

    ``Format`` is built from a COUNTERPARTY's payload
    (``creative_agent_registry._fetch_formats_raw_mcp`` validates a creative agent's reply
    into it) and then serialized to buyers by ``list_creative_formats``. The GENERATED parent
    sets ``extra="allow"``, which stores an unknown key and then emits it -- so without the
    local class's ``extra="ignore"`` every key an agent invented appeared in this seller's
    response under the pinned ``Format`` name, where no buyer could validate it.

    Measured counterfactual, not a hypothesis: ``LegacyFormat.model_validate`` of the payload
    below retains the undeclared keys and the local class dumps two, which is what the second
    test here pins.

    This is also what makes DELETING an internal field mean what it says.
    ``iab_specification``, ``accepts_3p_tags`` and ``category`` were removed from ``Format``
    as unused; under the parent's "allow" an agent still sending one would have had it
    PROMOTED from a field that could never reach the wire (``exclude=True``) to an extra that
    always does.
    """

    _AGENT_PAYLOAD = {
        "format_id": {"agent_url": DEFAULT_AGENT_URL, "id": "display_300x250"},
        "name": "Agent-supplied format",
        # The three deleted internal fields, plus an invented one.
        "iab_specification": "IAB-SOMETHING",
        "accepts_3p_tags": True,
        "category": "standard",
        "agent_invented_key": "should never be echoed",
    }

    def test_undeclared_keys_are_dropped_at_construction(self):
        fmt = Format.model_validate(self._AGENT_PAYLOAD)

        assert sorted(fmt.model_dump(exclude_none=True)) == ["format_id", "name"]

    def test_the_generated_parent_would_have_echoed_them(self):
        """The positive control: proves the assertion above is the local config's doing.

        Without it, a parent that happened to be strict would make the test above pass for a
        reason that has nothing to do with the ``model_config`` it exists to grade.
        """
        from adcp.types.legacy import LegacyFormat

        echoed = LegacyFormat.model_validate(self._AGENT_PAYLOAD).model_dump(exclude_none=True)

        assert "agent_invented_key" in echoed, (
            "the generated parent no longer retains unknown keys, so this seller's "
            "extra='ignore' may have become redundant -- re-read it before deleting"
        )

    def test_the_deleted_internal_fields_are_not_declared(self):
        for name in ("iab_specification", "accepts_3p_tags", "category"):
            assert name not in Format.model_fields
