"""Integration tests for the list_creatives concept_ids filter error path (#1407).

The happy path (filtering + concept_id/concept_name exposure) is covered by the
``@concept-id`` BDD storyboard scenario across a2a/mcp/rest. This module pins the
*error* path Chris flagged in review: a malformed ``filters.concept_ids`` (empty
array) violates the schema's ``minItems: 1`` and must be rejected — never silently
returning the whole library.

Two layers of guarantee:

1. **Rejected on every wire transport** (a2a/mcp/rest) — the malformed filter never
   degrades to "return everything".
2. **Spec two-layer ``VALIDATION_ERROR`` envelope with a recovery suggestion**
   (POST-F3) on every wire transport. REST and A2A coerce the wire dict through
   the shared ``coerce_creative_filters`` helper; MCP catches FastMCP TypeAdapter
   validation at the boundary and emits the same AdCP envelope.

Spec: ``core/creative-filters.json`` (concept_ids ``minItems: 1``) + the BR-UC-018
ext-c contract (validation failure → VALIDATION_ERROR + suggestion).

This module also hosts the list_creatives untyped-``data``-blob coercion guards: a
malformed ``concept_id``/``concept_name`` (``TestNumericConceptCoercion`` /
``TestNonScalarConceptValueDropped``, #1407), ``tags`` (``TestMalformedTagsBlobCoerced``)
or ``assets`` (``TestMalformedAssetsBlobCoerced``) value (#1508) in the blob must be
coerced or dropped-and-logged, never crash the whole listing on one bad row. Each guard
runs on every wire transport (a2a/mcp/rest): "the key is omitted" / "never null" is a
per-transport serialization claim, so REST-only would leave the MCP/A2A wire unproven.

Spec (coercion targets): pinned AdCP 3.1.1 (``adcp==6.6.0``, per docs/adcp-spec-version.md)
``creative/list-creatives-response.json`` types ``creatives[].tags`` as a non-nullable
``array<string>`` and ``creatives[].assets`` as an ``object`` — both optional (not in
``required``), so omission is conformant while ``null`` is not. Dropping corrupt internal
blob data to absent keeps the response conformant; it is robustness, not a contract change.
"""

import pytest

from tests.harness import CreativeListEnv, TransportResult
from tests.harness.transport import Transport
from tests.helpers import assert_envelope_shape

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# Wire transports only — IMPL has no wire envelope (and the dict→CreativeFilters
# coercion under test happens at the transport boundary, not in _impl).
_ALL_WIRE = [Transport.A2A, Transport.MCP, Transport.REST]


def _seed_authenticated_principal(env: CreativeListEnv):
    """Seed (and return) the tenant+principal the env authenticates as, so the
    request reaches filter validation / listing rather than failing auth first."""
    from tests.factories import PrincipalFactory, TenantFactory

    tenant = TenantFactory(tenant_id=env._tenant_id)
    principal = PrincipalFactory(tenant=tenant, principal_id=env._principal_id)
    return tenant, principal


def _list_single_creative_with_data(data: dict, transport: Transport) -> tuple[TransportResult, str]:
    """Seed one approved creative carrying *data* in its blob, list via *transport*, assert
    the listing did not error, and return ``(result, warnings_text)``.

    Collapses the seed-one-creative-and-list scaffold shared by the untyped-blob coercion
    guards (CLAUDE.md DRY): across those tests only the ``data`` literal and the per-test
    wire/log assertions vary. The module logger is patched (rather than captured via
    ``caplog``) so the drop-warning assertion is immune to the tox/integration logging
    config — levels/handlers/propagation/``logging.disable`` — that suppressed
    capture-based approaches. ``warnings_text`` is the ``logger.warning`` calls rendered
    to their final messages (``fmt % args``) so callers assert on the substituted text
    (the coercers pass the field label as a ``%s`` arg, not baked into the format string).

    Runs on any wire transport (callers parametrize over ``_ALL_WIRE``): ``"key" not in
    creative`` and stringify-not-null are per-transport serialization claims — omission
    survives MCP only via ``NestedModelSerializerMixin``, so a REST-only guard would leave
    the MCP/A2A wire unproven.
    """
    from unittest.mock import patch

    from tests.factories import CreativeFactory

    with CreativeListEnv() as env:
        tenant, principal = _seed_authenticated_principal(env)
        CreativeFactory(
            tenant=tenant,
            principal=principal,
            format="display_300x250",
            status="approved",
            data=data,
        )
        with patch("src.core.tools.creatives.listing.logger") as mock_logger:
            result = env.call_via(transport)

    # Assert the listing survived the bad row BEFORE rendering the captured warnings: a
    # real coercion regression must surface as this is-error failure (the listing crash the
    # guards exist to catch), not as a format-string error from the renderer below.
    assert not result.is_error, f"{transport}: listing errored on data={data!r}: {result.error!r}"
    # Render each warning to its final message. Guard the ``%`` substitution on presence of
    # format args (stdlib LogRecord.getMessage does the same via ``if self.args``) so a
    # legal zero/one-arg warning carrying a literal ``%`` cannot raise and mask the signal.
    warnings_text = " ".join(
        (call.args[0] % call.args[1:]) if len(call.args) > 1 else call.args[0]
        for call in mock_logger.warning.call_args_list
    )
    return result, warnings_text


class TestConceptIdsFilterValidation:
    """Malformed concept_ids filter is rejected, with a spec envelope on every wire transport."""

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_empty_concept_ids_array_is_rejected(self, integration_db, transport):
        """filters={'concept_ids': []} violates minItems:1 → rejected on every transport."""
        with CreativeListEnv() as env:
            _seed_authenticated_principal(env)

            result = env.call_via(transport, filters={"concept_ids": []})

            assert result.is_error, (
                f"{transport}: empty concept_ids must be rejected, not silently return the library; "
                f"got payload {result.payload!r}"
            )

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_empty_concept_ids_emits_validation_envelope(self, integration_db, transport):
        """Wire transports surface the two-layer VALIDATION_ERROR envelope with a suggestion."""
        with CreativeListEnv() as env:
            _seed_authenticated_principal(env)

            result = env.call_via(transport, filters={"concept_ids": []})

            envelope = result.wire_error_envelope
            assert envelope is not None, f"{transport}: no wire error envelope captured"
            assert_envelope_shape(envelope, "VALIDATION_ERROR", recovery="correctable")
            # POST-F3: the buyer is told how to recover. wire_error_envelope is always
            # a dict here (the AdCPToolError accessor lives in assert_envelope_shape).
            assert envelope["errors"][0].get("suggestion"), (
                f"{transport}: VALIDATION_ERROR envelope must carry a recovery suggestion: {envelope['errors'][0]}"
            )


class TestNumericConceptCoercion:
    """A numeric concept_id/concept_name in the data blob (CM360-style group ids) is
    coerced to the spec's string type, not crashed on. Regression guard for the #1
    fix: reverting the str()-coercion reddens this (the listing raises mid-build)."""

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_numeric_concept_id_is_coerced_to_string(self, integration_db, transport):
        result, warnings = _list_single_creative_with_data(
            {"assets": {}, "concept_id": 12345, "concept_name": 678}, transport
        )
        creative = result.wire_response["creatives"][0]
        assert creative["concept_id"] == "12345"
        assert creative["concept_name"] == "678"
        # Clean scalar input coerces silently — a coercer that logged a drop on a good row
        # (No Quiet Failures inverted into spurious noise) must redden here.
        assert warnings == "", f"{transport}: unexpected coercion warning on valid input: {warnings!r}"


class TestNonScalarConceptValueDropped:
    """A non-scalar concept_id/concept_name (corrupt external value) is dropped to
    null and logged, not projected as a repr and not crashed on — regression guard
    for the _coerce_blob_scalar non-scalar branch (the symmetric half of the
    numeric-coercion fix: reverting `return None` to a passthrough 500s the listing)."""

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_non_scalar_concept_value_is_dropped(self, integration_db, transport):
        result, warnings = _list_single_creative_with_data(
            {"assets": {}, "concept_id": ["x"], "concept_name": {"k": "v"}}, transport
        )
        creative = result.wire_response["creatives"][0]
        # Dropped to None → exclude_none omits the keys from the wire entirely.
        assert "concept_id" not in creative
        assert "concept_name" not in creative
        # Observability (No Quiet Failures): the drop is surfaced via the patched module
        # logger (see _list_single_creative_with_data on why not caplog), and each drop
        # names its OWN field — the wrapper that emitted a shared "concept" label for both
        # is retired, so a corrupt concept_id and concept_name are distinguishable (D1).
        assert "Dropping non-scalar concept_id value" in warnings
        assert "Dropping non-scalar concept_name value" in warnings


class TestSellerConceptEnrichmentIsFilterable:
    """The concept the #1506 merge helper writes is findable by the #1407 concept_ids
    filter and surfaced on the wire. This chains the merge helper's output → data blob
    → filter, so a key-name drift between the helper and the reader (e.g. writing
    ``concept`` while the filter reads ``concept_id``) reddens here. The full
    producer → real writeback → DB → reader chain (which this does NOT exercise — it
    calls the merge helper directly, not a writeback site) is pinned separately by
    ``test_execute_approved_platform_ids.py``."""

    def _enriched_data(self, order_id: str):
        from src.core.schemas import AssetStatus
        from src.core.tools.media_buy_create import _merge_creative_enrichment

        # The AssetStatus the GAM producer surfaces for a creative pushed into an order,
        # run through the real merge helper directly (the production writeback sites are
        # covered by test_execute_approved_platform_ids.py).
        status = AssetStatus(
            creative_id=f"gam_{order_id}",
            status="approved",
            concept_id=f"gam-order-{order_id}",
            concept_name=f"GAM Order {order_id}",
            concept_source="gam_order",
        )
        return _merge_creative_enrichment({"assets": {}}, status)

    def test_gam_order_concept_is_filterable_end_to_end(self, integration_db):
        from tests.factories import CreativeFactory

        with CreativeListEnv() as env:
            tenant, principal = _seed_authenticated_principal(env)
            CreativeFactory(
                tenant=tenant,
                principal=principal,
                format="display_300x250",
                status="approved",
                data=self._enriched_data("789"),
            )
            # A creative enriched from a different order must NOT match the filter.
            CreativeFactory(
                tenant=tenant,
                principal=principal,
                format="display_300x250",
                status="approved",
                data=self._enriched_data("000"),
            )

            result = env.call_via(Transport.REST, filters={"concept_ids": ["gam-order-789"]})

            assert not result.is_error, f"concept filter errored: {result.error!r}"
            creatives = result.wire_response["creatives"]
            assert len(creatives) == 1, f"expected only the order-789 creative, got {creatives!r}"
            assert creatives[0]["concept_id"] == "gam-order-789"
            assert creatives[0]["concept_name"] == "GAM Order 789"
            # The internal provenance marker must never reach the wire. Today it can't
            # (the reader projects explicit kwargs + the subclass extra="ignore" policy),
            # but nothing else pins it — a future schema change that echoed data must redden.
            assert "concept_source" not in creatives[0]


class TestMalformedTagsBlobCoerced:
    """A malformed ``tags`` value in the untyped ``data`` blob is coerced to a valid
    ``list[str]`` (or dropped to absent) and logged, never crashing the whole listing —
    #1508, the list-field sibling of the concept coercion guards above.

    ``Creative.tags`` is typed ``list[str] | None`` but read straight from the blob, so
    a bare string or a list carrying numeric/object elements would 500 the entire
    listing (``VALIDATION_ERROR``) during response construction. Reverting the
    ``_coerce_blob_str_list`` call at the ``tags=`` site back to the raw
    ``data.get("tags")`` reddens these tests (the listing raises mid-build)."""

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_non_list_tags_value_is_dropped(self, integration_db, transport):
        """A non-list tags blob (a bare string) is dropped to absent, not crashed on."""
        result, warnings = _list_single_creative_with_data({"assets": {}, "tags": "premium"}, transport)
        creative = result.wire_response["creatives"][0]
        # Dropped to None → exclude_none omits the key from the wire entirely.
        assert "tags" not in creative
        # Observability (No Quiet Failures): the drop is surfaced in logs, not silent.
        assert "Dropping non-list tags value" in warnings

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_non_string_tags_elements_are_coerced_or_dropped(self, integration_db, transport):
        """Scalar elements are stringified (bool included: ``str(True) == "True"``),
        non-scalar elements dropped+logged, order preserved."""
        result, warnings = _list_single_creative_with_data(
            {"assets": {}, "tags": [1, "keep", {"k": "v"}, True]}, transport
        )
        creative = result.wire_response["creatives"][0]
        # 1 -> "1", "keep" kept, {"k": "v"} dropped, True -> "True" (bool is an int
        # subclass); order preserved.
        assert creative["tags"] == ["1", "keep", "True"]
        assert "Dropping non-scalar tags value" in warnings

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_null_tags_element_is_dropped(self, integration_db, transport):
        """A JSON ``null`` element is corrupt for an ``items:{type:string}`` list (a null is
        not an absent value here) — dropped with a warning, the surviving elements kept,
        never silently swallowed. Removing the ``el is None`` drop branch leaves the element
        silently discarded (``["keep", null] -> ["keep"]`` with no log), reddening the log
        assertion."""
        result, warnings = _list_single_creative_with_data({"assets": {}, "tags": ["keep", None]}, transport)
        creative = result.wire_response["creatives"][0]
        assert creative["tags"] == ["keep"]
        assert "Dropping null tags element" in warnings

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_empty_tags_list_collapses_to_absent(self, integration_db, transport):
        """A stored empty tags list collapses to absent on the wire: ``exclude_none`` omits
        the key rather than emitting ``"tags": []``.

        The pinned 3.1.1 list-creatives-response schema permits both ``[]`` and omission;
        this pins the omission choice production made so it cannot silently drift back to
        ``[]`` (mutating the empty-list ``return None`` collapse to ``return coerced``
        reddens this test). The collapse is a valid-input serialization choice, not a
        corruption drop, so it must NOT emit a drop-warning — it logs at debug instead."""
        result, warnings = _list_single_creative_with_data({"assets": {}, "tags": []}, transport)
        creative = result.wire_response["creatives"][0]
        assert "tags" not in creative
        assert warnings == "", f"{transport}: empty-tags collapse must not warn: {warnings!r}"


class TestMalformedAssetsBlobCoerced:
    """A malformed ``assets`` value in the untyped ``data`` blob is dropped to absent and
    logged, never crashing the whole listing — #1508, the object-field sibling of the tags
    and concept coercion guards above.

    ``Creative.assets`` is typed ``dict[str, Any] | None`` but read straight from the same
    blob, so a stored non-dict (a list/string written by the same out-of-band producer)
    would 500 the entire listing during response construction. Reverting the
    ``_coerce_blob_dict`` call at the ``assets=`` site back to the raw ``assets_dict``
    reddens this (the listing raises mid-build)."""

    @pytest.mark.parametrize("transport", _ALL_WIRE)
    def test_non_dict_assets_value_is_dropped(self, integration_db, transport):
        result, warnings = _list_single_creative_with_data({"assets": ["not", "a", "dict"]}, transport)
        creative = result.wire_response["creatives"][0]
        # Dropped to None → exclude_none omits the key from the wire entirely.
        assert "assets" not in creative
        # Observability (No Quiet Failures): the drop is surfaced in logs, not silent.
        assert "Dropping non-dict assets value" in warnings
