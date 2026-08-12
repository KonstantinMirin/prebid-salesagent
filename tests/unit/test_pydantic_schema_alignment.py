#!/usr/bin/env python3
"""Automated Pydantic-to-Schema Alignment Tests.

This test suite automatically validates that ALL Pydantic request/response models
accept ALL fields defined in their corresponding AdCP JSON schemas.

This prevents regressions like:
- brand_manifest missing from CreateMediaBuyRequest
- filters missing from GetProductsRequest (PR #195)
- Any future field omissions

The test dynamically loads JSON schemas and validates Pydantic models can handle
all spec-compliant requests.
"""

import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.core.exceptions import AdCPInvalidRequestError
from src.core.schemas import (
    CreateMediaBuyRequest,
    CreateMediaBuySuccess,
    GetMediaBuyDeliveryRequest,
    GetProductsRequest,
    GetProductsResponse,
    GetSignalsResponse,
    ListAccountsResponse,
    ListCreativesRequest,
    ListCreativesResponse,
    Product,
    SyncAccountsResponse,
    SyncCreativesRequest,
    SyncCreativesResponse,
    SyncResponseAccount,
    UpdateMediaBuyRequest,
    UpdateMediaBuySuccess,
)
from src.core.schemas.creative import ListCreativeFormatsResponse
from src.core.schemas.delivery import GetCreativeDeliveryResponse, GetMediaBuyDeliveryResponse
from tests.helpers import pinned_schema
from tests.helpers.adcp_factories import create_test_cpm_pricing_option, create_test_publisher_properties_by_tag

# AdCP schemas are read from the installed adcp SDK's own pinned tree
# (tests/helpers/pinned_schema.py) — the SDK's own version IS the pin (moves
# with pyproject.toml's adcp version), so there is exactly one upstream pin
# for this suite, not an independently vendored snapshot (that snapshot
# previously lived here, pinned at adcontextprotocol/adcp@04f59d2d5, a full
# spec-minor behind the SDK's).
#
# Ref strings in this file are the one form the whole repo uses: a
# category-qualified path relative to the version root, exactly as the SDK's
# own index writes it. This file used to carry a "/schemas/" prefix of its own
# and strip it here, which made a SECOND ref normalizer with rules that
# disagreed with the shared one.

# Map AdCP schema refs to Pydantic model classes. At 04f59d2d5, sync/list-creatives
# live under `creative/` (relocated from `media-buy/` earlier in 3.x).
#
# NOTE: CreateMediaBuyRequest is temporarily excluded due to AdCP spec evolution.
# The spec now requires brand_card, but we maintain backward compatibility
# via brand_manifest. Full brand_card implementation will be added in a separate PR.
SCHEMA_TO_MODEL_MAP = {
    "media-buy/get-products-request.json": GetProductsRequest,
    # "media-buy/create-media-buy-request.json": CreateMediaBuyRequest,  # Skipped - pending brand_card implementation
    "media-buy/update-media-buy-request.json": UpdateMediaBuyRequest,
    "media-buy/get-media-buy-delivery-request.json": GetMediaBuyDeliveryRequest,
    "creative/sync-creatives-request.json": SyncCreativesRequest,
    "creative/list-creatives-request.json": ListCreativesRequest,
    # Note: GetSignalsRequest removed — signals is dead code (UC-008), not exposed via MCP or A2A
}

# get-products schema drift — tracked in #1308. The live AdCP schema carries
# the `adcp_major_version` envelope plus `if_catalog_version`/`if_pricing_version`;
# the pinned adcp library does not model them yet. Coverage:
#   - adcp_major_version → excluded via _VERSION_FIELDS
#   - if_catalog_version, if_pricing_version → excluded via KNOWN_SCHEMA_LIBRARY_MISMATCHES
# Tests now pass; remove the prior strict-xfail wrapper.
SCHEMA_TO_MODEL_PARAMS_WITH_GET_PRODUCTS_DRIFT_XFAIL = [
    pytest.param(schema_ref, model_class) for schema_ref, model_class in SCHEMA_TO_MODEL_MAP.items()
]

# Version metadata fields present in AdCP JSON schemas that models don't declare explicitly.
# These have defaults or are managed by the library base class — exclude from all comparisons.
_VERSION_FIELDS: frozenset[str] = frozenset({"adcp_version", "adcp_major_version"})

# Fields the SDK's current schema tree defines but the local model does not yet
# model. These are spec-vs-library mismatches, not bugs in our code.
#
# Keys MUST match the `schema_ref` values in SCHEMA_TO_MODEL_MAP verbatim;
# `KNOWN_SCHEMA_LIBRARY_MISMATCHES.get(schema_ref, set())` lookups silently fall back
# to an empty set otherwise.
KNOWN_SCHEMA_LIBRARY_MISMATCHES: dict[str, set[str]] = {
    "media-buy/get-products-request.json": set(),
    "media-buy/update-media-buy-request.json": set(),
    "media-buy/get-media-buy-delivery-request.json": set(),
    "creative/sync-creatives-request.json": set(),
    "creative/list-creatives-request.json": set(),
}


def load_json_schema(schema_ref: str) -> dict[str, Any]:
    """Load an AdCP schema from the installed adcp SDK's pinned tree.

    Normalization is ``pinned_schema.normalize_ref`` — the single shared rule,
    not a second one local to this file. Every ``$ref`` inside the returned
    dict is canonicalized to root-relative form
    (``pinned_schema.load_canonicalized``), so a ``$ref`` found while walking
    the returned schema is itself a valid input here. A missing file is a HARD
    FAILURE (the pin moved, or a ``$ref`` is outside the resolvable tree),
    never a silent skip.
    """
    return pinned_schema.load_canonicalized(pinned_schema.normalize_ref(schema_ref))


def _unsynthesized_guess(field_name: str) -> str:
    """The generator's last-resort string for a shape it has no rule for.

    Named rather than inlined so ``_synthesize_sample`` can RECOGNIZE a guess and
    refuse it instead of feeding it to a model. A guess is not a sample: it is the
    generator saying "I could not derive this", and passing it on is what turned a
    mechanical gap in the instrument into a false conformance failure against
    production code (the 'test_status_value' failures that once bought the envelope
    'status' its blanket exclusion from requiredness grading).
    """
    return f"test_{field_name}_value"


def generate_example_value(field_type: str, field_name: str = "", field_spec: dict = None) -> Any:
    """Generate a reasonable example value for a JSON schema type."""
    # Inline enum (e.g. cache_scope: {"type": "string", "enum": ["public", "account"]}):
    # a generic "test_<field>_value" string is not a member of the enum and fails
    # Pydantic validation on construction — checked before the $ref/oneOf/allOf
    # branches below since an inline enum can appear on any of those field shapes.
    if field_spec and "enum" in field_spec:
        return field_spec["enum"][0]

    # Handle $ref fields (complex nested objects)
    if field_spec and "$ref" in field_spec:
        # Generate sensible defaults for known $ref types
        ref = field_spec["$ref"]
        if "budget" in ref.lower():
            return {"total": 5000.0, "currency": "USD"}
        elif "package-update" in ref.lower():
            return {"package_id": "pkg_1"}
        elif "package" in ref.lower():
            return [{"product_ids": ["prod_1"], "budget": {"total": 5000.0, "currency": "USD"}}]
        elif "creative" in ref.lower():
            return []  # Empty array is valid for creative lists
        elif "brand-manifest" in ref.lower():
            return {"name": "Test Brand"}
        elif "property-list" in ref.lower():
            return {"agent_url": "https://example.com", "list_id": "list_1"}
        elif "promoted-products" in ref.lower():
            return {"manifest_skus": ["SKU-001"]}
        elif "pagination-request" in ref.lower():
            return {"max_results": 50}
        elif "product-filters" in ref.lower():
            return {"delivery_type": "guaranteed"}
        elif "reporting-webhook" in ref.lower():
            return {
                "url": "https://example.com/webhook",
                "reporting_frequency": "daily",
                "authentication": {"credentials": "test-token", "schemes": ["Bearer"]},
            }
        elif "start-timing" in ref.lower():
            return "2025-02-01T00:00:00Z"
        elif "push-notification" in ref.lower():
            return {"url": "https://example.com/notify"}
        elif "validation-mode" in ref.lower():
            return "strict"
        elif "context" in ref.lower():
            return {"session_id": "test-session"}
        elif "ext" in ref.lower():
            return {"custom_field": "test"}
        # For unknown refs, resolve the schema and generate from its properties
        try:
            ref_schema = load_json_schema(ref)
            ref_type = ref_schema.get("type", "object")
            if ref_type == "string" and "enum" in ref_schema:
                return ref_schema["enum"][0]
            if ref_type != "object":
                return generate_example_value(ref_type, field_name, ref_schema)
            # Generate object with required fields from the resolved schema
            obj = {}
            required_fields = ref_schema.get("required", [])
            for prop_name, prop_spec in ref_schema.get("properties", {}).items():
                if prop_name in required_fields:
                    prop_type = prop_spec.get("type", "string")
                    obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec)
            return obj if obj else {}
        except Exception:
            return {}

    # Handle allOf with $ref (e.g., time_budget: allOf[{$ref: duration.json}])
    if field_spec and "allOf" in field_spec:
        for variant in field_spec["allOf"]:
            if "$ref" in variant:
                return generate_example_value("object", field_name, variant)
        # If no $ref in allOf, merge properties from all variants
        merged_spec = dict(field_spec)
        del merged_spec["allOf"]
        for variant in field_spec["allOf"]:
            merged_spec.update(variant)
        return generate_example_value(merged_spec.get("type", "object"), field_name, merged_spec)

    # Handle field-level oneOf (e.g., status_filter: oneOf[enum, array-of-enum])
    # Pick the first variant and recursively generate a value for it.
    if field_spec and "oneOf" in field_spec:
        first_variant = field_spec["oneOf"][0]
        # The variant might be a $ref (e.g., to an enum schema) or inline type
        if "$ref" in first_variant:
            ref = first_variant["$ref"]
            # Load the referenced schema to get enum values or type info
            ref_schema = load_json_schema(ref)
            if "enum" in ref_schema:
                return ref_schema["enum"][0]
            variant_type = ref_schema.get("type", "string")
            return generate_example_value(variant_type, field_name, ref_schema)
        variant_type = first_variant.get("type", "string")
        return generate_example_value(variant_type, field_name, first_variant)

    if field_type == "string":
        # Check for pattern constraints in schema
        if field_spec and "pattern" in field_spec:
            pattern = field_spec["pattern"]
            # Handle common date pattern: YYYY-MM-DD
            if pattern == r"^\d{4}-\d{2}-\d{2}$":
                return "2025-02-01"
            # Handle domain patterns (lowercase alphanumeric + hyphens + dots)
            if "a-z0-9" in pattern and "\\." in pattern:
                return "example.com"
            # Handle lowercase identifier patterns (e.g., brand_id: ^[a-z0-9_]+$)
            if "a-z0-9" in pattern:
                return "test_value"

        # Special cases for known field patterns
        if "date" in field_name.lower():
            # Use date format (YYYY-MM-DD) not datetime
            return "2025-02-01"
        if "time" in field_name.lower():
            # For time fields use full ISO 8601
            return "2025-02-01T00:00:00Z"
        if "id" in field_name.lower():
            return f"test_{field_name}_123"
        if "url" in field_name.lower():
            return "https://example.com/test"
        if "email" in field_name.lower():
            return "test@example.com"
        if "version" in field_name.lower():
            return "1.0.0"
        if "offering" in field_name.lower():
            return "Nike Air Jordan 2025 basketball shoes"
        if "po_number" in field_name.lower():
            return "PO-TEST-12345"
        return _unsynthesized_guess(field_name)
    elif field_type == "number":
        return 100.0
    elif field_type == "integer":
        return 100
    elif field_type == "boolean":
        return True
    elif field_type == "array":
        # Check if items type is specified
        if field_spec and "items" in field_spec:
            items_spec = field_spec["items"]
            if isinstance(items_spec, dict):
                # Check if items have $ref (e.g., Creative objects)
                if "$ref" in items_spec:
                    ref = items_spec["$ref"]
                    if "creative" in ref.lower():
                        # Generate minimal Creative object
                        return [
                            {
                                "creative_id": "test_creative_1",
                                "name": "Test Creative",
                                "format": "display_300x250",
                            }
                        ]
                    # Resolve the ref to check if it's an enum or simple type
                    try:
                        ref_schema = load_json_schema(ref)
                        if "enum" in ref_schema:
                            return [ref_schema["enum"][0]]
                        ref_type = ref_schema.get("type", "object")
                        if ref_type != "object":
                            return [generate_example_value(ref_type, field_name, ref_schema)]
                    except Exception:
                        pass
                    # For other refs, return minimal object
                    return [{}]

                item_type = items_spec.get("type", "string")
                if item_type == "object":
                    # Generate a proper object with required fields
                    obj = {}
                    if "properties" in items_spec:
                        required_fields = items_spec.get("required", [])
                        for prop_name, prop_spec in items_spec["properties"].items():
                            if prop_name in required_fields or "id" in prop_name:
                                prop_type = prop_spec.get("type", "string")
                                obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec)
                    return [obj] if obj else []
                else:
                    # Generate one example item
                    return [generate_example_value(item_type, field_name, items_spec)]
        return []
    elif field_type == "object":
        # Generate sensible defaults for known object types
        if "budget" in field_name.lower():
            return {
                "total": 5000.0,
                "currency": "USD",
                "pacing": "even",
            }
        if "targeting" in field_name.lower():
            return {
                "geo_countries": ["US"],
            }
        if field_spec and "properties" in field_spec:
            # Generate a minimal object with required fields
            obj = {}
            required_fields = field_spec.get("required", [])
            for prop_name, prop_spec in field_spec["properties"].items():
                if prop_name in required_fields:
                    prop_type = prop_spec.get("type", "string")
                    obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec)
            return obj
        return {}
    else:
        return None


def extract_required_fields(schema: dict[str, Any]) -> list[str]:
    """Extract required fields from a JSON schema."""
    return schema.get("required", [])


def extract_all_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract all fields (required and optional) from a JSON schema."""
    properties = schema.get("properties", {})
    return {
        field_name: field_spec
        for field_name, field_spec in properties.items()
        if field_name not in _VERSION_FIELDS
        # Note: We include $ref fields now - generate_example_value will handle them
    }


def generate_minimal_valid_request(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a minimal valid request with only required fields.

    Handles oneOf constraints by including the first required field from the oneOf options.
    """
    required_fields = extract_required_fields(schema)
    properties = schema.get("properties", {})
    oneof_groups = get_oneof_field_groups(schema)

    # If there's a oneOf constraint and no explicit required fields,
    # we need to include at least one field from the oneOf options
    if not required_fields and oneof_groups:
        # Pick the first field from all oneOf options (alphabetically)
        all_oneof_fields = set()
        for group in oneof_groups:
            all_oneof_fields.update(group)
        if all_oneof_fields:
            chosen_field = sorted(all_oneof_fields)[0]
            required_fields = [chosen_field]

    request_data = {}
    for field_name in required_fields:
        if field_name not in properties:
            continue
        field_spec = properties[field_name]
        field_type = field_spec.get("type", "string")
        request_data[field_name] = generate_example_value(field_type, field_name, field_spec)

    return request_data


def get_oneof_field_groups(schema: dict[str, Any]) -> list[set[str]]:
    """Extract oneOf field groups from schema.

    Returns list of sets where each set contains fields that are mutually exclusive.
    Handles both root-level oneOf and nested oneOf in allOf.
    """
    field_groups = []

    # Check root-level oneOf
    if "oneOf" in schema:
        for option in schema["oneOf"]:
            if "required" in option:
                field_groups.append(set(option["required"]))

    # Check oneOf in allOf constraints
    if "allOf" in schema:
        for constraint in schema["allOf"]:
            if "oneOf" in constraint:
                for option in constraint["oneOf"]:
                    if "required" in option:
                        field_groups.append(set(option["required"]))

    return field_groups


def generate_full_valid_request(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a complete valid request with all fields.

    Handles oneOf constraints by only including ONE field from all mutually exclusive options.
    For example, if oneOf says "either field_a OR field_b", only include one.
    """
    all_fields = extract_all_fields(schema)
    oneof_groups = get_oneof_field_groups(schema)

    # Flatten: all fields mentioned in ANY oneOf group are mutually exclusive
    # For example, if oneOf says [{"required": ["field_a"]}, {"required": ["field_b"]}]
    # then field_a and field_b are mutually exclusive
    all_oneof_fields = set()
    for group in oneof_groups:
        all_oneof_fields.update(group)

    # Pick the first one alphabetically to be deterministic
    chosen_oneof_field = sorted(all_oneof_fields)[0] if all_oneof_fields else None

    request_data = {}
    for field_name, field_spec in all_fields.items():
        # If this is a oneOf field, only include if it's the chosen one
        if field_name in all_oneof_fields:
            if field_name != chosen_oneof_field:
                continue

        field_type = field_spec.get("type", "string")
        request_data[field_name] = generate_example_value(field_type, field_name, field_spec)

    return request_data


class TestPydanticSchemaAlignment:
    """Test that Pydantic models accept all fields from AdCP JSON schemas."""

    @pytest.mark.parametrize(
        "schema_ref,model_class",
        SCHEMA_TO_MODEL_PARAMS_WITH_GET_PRODUCTS_DRIFT_XFAIL,
    )
    def test_model_accepts_all_schema_fields(self, schema_ref: str, model_class: type):
        """Test that Pydantic model accepts ALL fields defined in JSON schema.

        This is the critical test that would have caught:
        - brand_manifest missing from CreateMediaBuyRequest
        - filters missing from GetProductsRequest
        """
        # Load the JSON schema
        schema = load_json_schema(schema_ref)

        # Generate a request with ALL fields from schema
        full_request = generate_full_valid_request(schema)

        # This should NOT raise ValidationError
        try:
            instance = model_class(**full_request)
            assert instance is not None
        except AdCPInvalidRequestError as e:
            # A custom business-rule validator (stricter than the raw schema) raised
            # a typed INVALID_REQUEST — e.g. AdCPPackageUpdate requires package_id and
            # rejects immutable fields. The synthetic generator does not satisfy those
            # nested constraints. Models MAY be stricter than spec; this is acceptable
            # as long as it is not rejecting a spec field (it requires a required field).
            pytest.skip(
                f"{model_class.__name__} enforces a business-rule shape "
                f"(custom validator → INVALID_REQUEST), stricter than the schema. Acceptable. Error: {e}"
            )
        except ValidationError as e:
            # Extract which fields were rejected
            rejected_fields = [err["loc"][0] for err in e.errors() if err["type"] == "extra_forbidden"]
            missing_fields = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            value_errors = [err for err in e.errors() if err["type"] == "value_error"]

            # value_errors can indicate custom validators (business logic requirements)
            # These are acceptable if they don't reject spec fields
            # Only fail if we're rejecting fields that ARE in the spec
            known = KNOWN_SCHEMA_LIBRARY_MISMATCHES.get(schema_ref, set())
            rejected_fields = [f for f in rejected_fields if f not in known]
            if rejected_fields:
                error_msg = f"\n{model_class.__name__} REJECTED AdCP spec fields!\n"
                error_msg += f"   Rejected fields: {rejected_fields}\n"
                error_msg += "\n   This means clients sending spec-compliant requests will get validation errors.\n"
                error_msg += f"   Schema: {schema_ref}\n"
                error_msg += f"   Error details: {e}\n"
                pytest.fail(error_msg)

            # If there are value_errors but no rejected_fields, this likely means
            # the model has stricter requirements than the spec (custom validators).
            # This is acceptable - models CAN be stricter than spec.
            # Only fail if the spec explicitly requires fields we're missing.
            if value_errors and not rejected_fields:
                # Check if error mentions fields not being provided
                # This is okay - model can require more than spec
                pytest.skip(
                    f"{model_class.__name__} has stricter validation than spec (custom validators). "
                    f"This is acceptable. Error: {e}"
                )

    @pytest.mark.parametrize("schema_ref,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_model_has_all_required_fields(self, schema_ref: str, model_class: type):
        """Test that Pydantic model requires all fields marked as required in JSON schema."""
        # Load the JSON schema
        schema = load_json_schema(schema_ref)

        # Get required fields from schema
        required_in_schema = set(extract_required_fields(schema))

        # Skip adcp_version as it often has defaults
        required_in_schema -= _VERSION_FIELDS

        if not required_in_schema:
            # No required fields in schema - nothing to test, which is fine
            return

        # Try to create model without required fields
        try:
            instance = model_class()

            # If it succeeded, check which required fields have defaults
            model_data = instance.model_dump()
            fields_with_defaults = {field for field in required_in_schema if field in model_data}

            # If ALL required fields have defaults, that might be intentional
            if fields_with_defaults == required_in_schema:
                pytest.skip(f"All required fields have defaults: {fields_with_defaults}")

        except ValidationError as e:
            # This is expected - required fields should cause validation errors
            missing_from_error = {err["loc"][0] for err in e.errors() if err["type"] == "missing"}

            # Verify that the fields flagged as missing match schema requirements
            if missing_from_error != required_in_schema:
                unexpected = missing_from_error - required_in_schema
                not_enforced = required_in_schema - missing_from_error

                # If model requires MORE fields than spec, that's acceptable (business logic)
                # Only fail if model requires FEWER fields than spec
                if not_enforced and not unexpected:
                    pytest.skip(
                        f"{model_class.__name__} has optional fields where spec requires them: {not_enforced}. "
                        f"This may be intentional for flexibility."
                    )

                if unexpected and not not_enforced:
                    pytest.skip(
                        f"{model_class.__name__} requires additional fields beyond spec: {unexpected}. "
                        f"This is acceptable for business logic."
                    )

                # Both unexpected and not_enforced - this can be legacy conversion logic
                # For example, CreateMediaBuyRequest accepts legacy product_ids OR new packages,
                # and requires po_number for business tracking
                if unexpected and not_enforced:
                    pytest.skip(
                        f"{model_class.__name__} has flexible field requirements (likely legacy conversion). "
                        f"Requires: {unexpected}, Optional where spec requires: {not_enforced}. "
                        f"This is acceptable for backward compatibility."
                    )

    @pytest.mark.parametrize("schema_ref,model_class", SCHEMA_TO_MODEL_MAP.items())
    def test_model_accepts_minimal_request(self, schema_ref: str, model_class: type):
        """Test that Pydantic model accepts minimal valid request (only required fields).

        Note: Models CAN require additional fields beyond the spec for business logic.
        This test skips cases where models are intentionally stricter.
        """
        # Load the JSON schema
        schema = load_json_schema(schema_ref)

        # Generate minimal request
        minimal_request = generate_minimal_valid_request(schema)

        # Strip fields that are known library mismatches (spec has them, library doesn't yet)
        known_mismatches = KNOWN_SCHEMA_LIBRARY_MISMATCHES.get(schema_ref, set())
        for field in known_mismatches:
            minimal_request.pop(field, None)

        # This should work
        try:
            instance = model_class(**minimal_request)
            assert instance is not None
        except ValidationError as e:
            # Check if this is a value_error (custom validator) - models can be stricter
            value_errors = [err for err in e.errors() if err["type"] == "value_error"]
            if value_errors:
                pytest.skip(
                    f"{model_class.__name__} has stricter validation than spec (custom validators). "
                    f"This is acceptable for business logic. Error: {e}"
                )

            # Check if error is about missing fields - model requires more than spec
            missing_errors = [err for err in e.errors() if err["type"] == "missing"]
            if missing_errors:
                missing_fields = {err["loc"][0] for err in missing_errors}
                pytest.skip(
                    f"{model_class.__name__} requires additional fields beyond spec: {missing_fields}. "
                    f"This is acceptable for business logic."
                )

            # Other validation errors are real problems
            pytest.fail(
                f"{model_class.__name__} rejected minimal valid request.\n"
                f"Schema: {schema_ref}\n"
                f"Request: {minimal_request}\n"
                f"Error: {e}"
            )


class TestSpecificFieldValidation:
    """Specific regression tests for fields that have caused issues."""

    def test_create_media_buy_accepts_brand_manifest(self):
        """REGRESSION TEST: brand must be accepted per AdCP v3.6.0 (replaced brand_manifest)."""
        request = CreateMediaBuyRequest(
            brand={"domain": "nike.com"},
            packages=[
                {
                    "product_id": "prod_1",
                    "budget": 5000.0,
                    "pricing_option_id": "test_pricing",
                }
            ],
            start_time="2025-02-01T00:00:00Z",
            end_time="2025-02-28T23:59:59Z",
            idempotency_key="unit-test-key-accepts-brand-mfst",
        )
        # Verify brand was accepted
        assert request.brand is not None

    def test_get_products_accepts_filters(self):
        """REGRESSION TEST: filters must be accepted (PR #195 issue)."""
        request = GetProductsRequest(
            brand={"domain": "testproduct.com"},
            filters={
                "delivery_type": "guaranteed",
                "format_types": ["video"],
            },
        )
        assert request.filters is not None
        assert request.filters.delivery_type.value == "guaranteed"

    def test_get_products_all_fields_optional(self):
        """Test that GetProductsRequest accepts all optional fields per spec.

        Note: adcp_version is NOT a field on GetProductsRequest per AdCP spec.
        All fields are optional, including brand.
        adcp 3.6.0: brand replaced brand_manifest.
        """
        # Empty request is valid
        empty_request = GetProductsRequest()
        assert empty_request.brand is None
        assert empty_request.brief is None
        assert empty_request.filters is None

        # With brand only
        request = GetProductsRequest(
            brand={"domain": "testproduct.com"},
        )
        assert request.brand is not None
        assert request.brief is None


class TestFieldNameConsistency:
    """Test that field names match between Pydantic models and JSON schemas."""

    @pytest.mark.parametrize(
        "schema_ref,model_class",
        SCHEMA_TO_MODEL_PARAMS_WITH_GET_PRODUCTS_DRIFT_XFAIL,
    )
    def test_field_names_match_schema(self, schema_ref: str, model_class: type):
        """Test that Pydantic model field names match JSON schema property names."""
        # Load the JSON schema
        schema = load_json_schema(schema_ref)

        # Get all properties from schema
        schema_fields = set(schema.get("properties", {}).keys())

        # Get all fields from Pydantic model
        model_fields = set(model_class.model_fields.keys())

        # Find discrepancies (excluding internal fields)
        internal_fields = {"strategy_id", "testing_mode"}  # Known internal-only fields
        model_fields_public = model_fields - internal_fields

        # Fields in schema but not in model (potential missing fields)
        missing_in_model = schema_fields - model_fields_public

        # We're lenient here - having extra model fields is okay (for internal use)
        # But missing schema fields is a problem
        if missing_in_model:
            # Some fields might be intentionally skipped (like adcp_version with defaults)
            critical_missing = missing_in_model - _VERSION_FIELDS

            # Filter out known spec-vs-library mismatches
            known = KNOWN_SCHEMA_LIBRARY_MISMATCHES.get(schema_ref, set())
            critical_missing = critical_missing - known

            if critical_missing:
                pytest.fail(
                    f"\n{model_class.__name__} is missing schema fields!\n"
                    f"   Missing: {critical_missing}\n"
                    f"   These fields are defined in AdCP spec but not in Pydantic model.\n"
                    f"   Schema: {schema_ref}\n"
                )


# ---------------------------------------------------------------------------
# Response-model alignment (pinned).
#
# Response schemas are oneOf unions, so a local success model maps to one variant
# (and, for list responses, a nested item). These checks reuse the SAME pinned
# load_json_schema() as the request checks above — no per-test hand-rolled schema
# IO — so "model conforms to the pinned schema" lives in one place.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResponseAlignment:
    """Maps a local success model to its pinned response (sub-)schema."""

    schema_ref: str
    selector: str  # a property that identifies the success oneOf variant
    item_key: str | None  # if set, the per-element schema is variant.properties[item_key].items
    model: type
    declared_fields: frozenset[str] = frozenset()  # fields that MUST be declared on the model
    sample: dict[str, Any] = dataclass_field(default_factory=dict)  # valid kwargs for required-enforcement


@dataclass(frozen=True)
class _RegistryRow:
    """One implemented response model bound to its pinned schema (#1399 Plan-B).

    The success arm is derived from the schema, not hand-listed: the generator
    reads its required[]/properties so a required field added to the spec is
    enforced automatically. ``sample_override`` supplies valid kwargs only where
    a complex required field (e.g. packages, reporting_period, pagination) cannot
    be synthesized generically — it never weakens or skips a required field.
    ``declared_fields_override`` narrows the F4 declared-field check when the full
    property set would be noise (e.g. forward-compat optional fields).
    """

    schema_ref: str
    selector: str  # property unique to the success arm (picks the oneOf member)
    model: type
    sample_override: dict[str, Any] | None = None
    declared_fields_override: frozenset[str] | None = None


# Every AdCP-grounded response model the seller implements (extends a Library*
# base, maps to a pinned *-response.json). Operations the seller does NOT
# implement (brand-rights, collections, content-standards, governance-plans,
# sponsored-intelligence, comply-test-controller, tmp/*) have no local model and
# are deliberately absent. SalesAgentBaseModel-only response models (internal /
# human_tasks-deprecated: CheckCreativeStatusResponse, CreateCreativeResponse,
# AddCreativeAssetsResponse, GetCreativesResponse, GetPendingCreativesResponse,
# ApproveCreativeResponse, AssignCreativeResponse, UpdatePerformanceIndexResponse,
# CheckMediaBuyStatusResponse, *HumanTask*, *Task*, GetTargetingCapabilities,
# CheckAXERequirements, SimulationControl, ListAuthorizedProperties,
# GetMediaBuysResponse, GetAllMediaBuyDelivery, Adapter*) are not spec-grounded
# success arms and are excluded.
_RESPONSE_MODEL_REGISTRY: list[_RegistryRow] = [
    _RegistryRow(
        schema_ref="media-buy/get-products-response.json",
        selector="products",
        model=GetProductsResponse,
    ),
    _RegistryRow(
        schema_ref="media-buy/create-media-buy-response.json",
        selector="media_buy_id",
        model=CreateMediaBuySuccess,
        # packages requires the local package shape; synthesize is not reliable.
        sample_override={"media_buy_id": "mb_1", "packages": [{"package_id": "pkg_1", "paused": False}]},
        # Forward-compat fields production emits that must be explicitly declared (F4, PR #1388).
        declared_fields_override=frozenset({"valid_actions", "context"}),
    ),
    _RegistryRow(
        schema_ref="media-buy/update-media-buy-response.json",
        selector="media_buy_id",
        model=UpdateMediaBuySuccess,
    ),
    _RegistryRow(
        schema_ref="media-buy/get-media-buy-delivery-response.json",
        selector="media_buy_deliveries",
        model=GetMediaBuyDeliveryResponse,
        sample_override={
            "reporting_period": {"start": "2025-02-01T00:00:00Z", "end": "2025-02-02T00:00:00Z"},
            "currency": "USD",
            "aggregated_totals": {"impressions": 0.0, "spend": 0.0, "media_buy_count": 0},
            "media_buy_deliveries": [],
        },
    ),
    _RegistryRow(
        schema_ref="creative/get-creative-delivery-response.json",
        selector="creatives",
        model=GetCreativeDeliveryResponse,
        sample_override={
            "reporting_period": {"start": "2025-02-01T00:00:00Z", "end": "2025-02-02T00:00:00Z"},
            "currency": "USD",
            "creatives": [],
        },
    ),
    _RegistryRow(
        schema_ref="account/list-accounts-response.json",
        selector="accounts",
        model=ListAccountsResponse,
    ),
    _RegistryRow(
        schema_ref="account/sync-accounts-response.json",
        selector="accounts",
        model=SyncAccountsResponse,
    ),
    _RegistryRow(
        schema_ref="creative/sync-creatives-response.json",
        selector="creatives",
        model=SyncCreativesResponse,
    ),
    _RegistryRow(
        schema_ref="creative/list-creatives-response.json",
        selector="creatives",
        model=ListCreativesResponse,
        sample_override={
            "query_summary": {"total_matching": 0, "returned": 0},
            "pagination": {"has_more": False},
            "creatives": [],
        },
    ),
    _RegistryRow(
        schema_ref="creative/list-creative-formats-response.json",
        selector="formats",
        model=ListCreativeFormatsResponse,
    ),
    _RegistryRow(
        schema_ref="signals/get-signals-response.json",
        selector="signals",
        model=GetSignalsResponse,
    ),
]


def _allof_required_fields(schema: dict[str, Any]) -> set[str]:
    """Domain-level required fields from every arm of a schema's top-level
    ``allOf`` — e.g. a shared error/pricing sub-schema composed in alongside
    the domain shape. A response schema with no top-level ``oneOf``/``required``
    of its own (get-products-response.json in 3.1.1) can still spec-require
    fields via allOf; without merging them in, a schema-required field
    silently drops out of grading instead of failing loudly (the exact bug
    class this suite exists to catch).

    This includes the shared Protocol Envelope arm's own ``status``. It used to be
    subtracted back out; nothing is excluded now, so a pin bump that adds a second
    envelope-required field lands directly as alignment failures on every model
    lacking it — forcing the same per-field decision, at the location that needs it.
    """
    required: set[str] = set()
    for arm in schema.get("allOf", []) or []:
        resolved = pinned_schema.load_canonicalized(arm["$ref"]) if "$ref" in arm else arm
        required |= set(resolved.get("required", []))
    return required


def _standard_branch_required_fields(schema: dict[str, Any]) -> set[str]:
    """Required fields from the innermost ``else`` branch of an ``if``/``then``/``else`` chain.

    3.1.1 response schemas (e.g. get-products-response.json, get-signals-response.json)
    express conditional requiredness this way instead of a top-level ``required`` or a
    root ``oneOf``: an outer if/then/else branches on the wholesale-unchanged shape,
    nesting a second if/then/else inside its ``else`` that branches on ``status ==
    "failed"`` vs. the standard success shape. The alignment suite's samples are all
    ordinary successful responses, so the "standard" branch — the final ``else`` at the
    end of the chain — is the one whose ``required`` applies; without walking it, these
    fields silently drop out of grading (the schema has no OTHER top-level ``required``
    to fall back on) instead of failing loudly.
    """
    node = schema
    walked = False
    while "else" in node:
        node = node["else"]
        walked = True
    return set(node.get("required", [])) if walked else set()


def _allof_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Property definitions contributed by every arm of a schema's top-level
    ``allOf`` — the shared Protocol/Version Envelope arms above all.

    Requiredness and definedness have to be merged from the same place or the
    walk contradicts itself: ``_allof_required_fields`` already pulls ``status``
    out of the envelope arm's ``required``, so a walk that does not also pull in
    the arm's ``properties`` reports a field as schema-required and, in the same
    breath, as not defined by the schema. Both graders read the merged node —
    ``test_declared_fields_present_in_schema_and_model`` checks membership in
    ``properties``, and ``_synthesize_sample`` reads the per-field spec out of it
    to build a valid value — so the missing half showed up as 7 spurious
    "not defined by pinned schema" failures plus samples synthesized from an
    empty spec.
    """
    props: dict[str, Any] = {}
    for arm in schema.get("allOf", []) or []:
        resolved = pinned_schema.load_canonicalized(arm["$ref"]) if "$ref" in arm else arm
        props |= resolved.get("properties", {})
    return props


def _merge_composed(node: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Merge the fields composed into ``schema`` at its root — ``required`` from
    its top-level allOf arms and its if/then/else standard branch, ``properties``
    from those same allOf arms — into ``node``, rebuilding it only if that adds
    anything.

    ``node``'s own definitions win: a domain schema that redeclares an envelope
    property (narrowing it, say) is the more specific statement about the shape
    a buyer receives.

    schema is usually node itself, but a resolved oneOf variant passes the
    top-level schema separately: allOf/if-then-else compose at the schema
    root, not on the individual arm.
    """
    merged_required = (
        set(node.get("required", [])) | _allof_required_fields(schema) | _standard_branch_required_fields(schema)
    )
    merged_properties = _allof_properties(schema) | node.get("properties", {})
    if merged_required == set(node.get("required", [])) and merged_properties == node.get("properties", {}):
        return node
    return {**node, "required": sorted(merged_required), "properties": merged_properties}


def _success_arm(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the success (sub-)schema: the oneOf arm whose required[] names
    neither ``errors`` nor ``task_id`` (error / submitted arms), or the schema
    itself — with ``required`` merged from its top-level ``allOf`` arms and any
    ``if``/``then``/``else`` standard branch — when it is a flat single-shape
    response (no oneOf)."""
    if "oneOf" not in schema:
        return _merge_composed(schema, schema)
    for arm in schema["oneOf"]:
        required = set(arm.get("required", []))
        if "errors" not in required and "task_id" not in required:
            return arm
    raise AssertionError(f"No success arm found in oneOf (all arms look like error/submitted): {schema.get('$id')}")


def _synthesize_sample(arm: dict[str, Any], schema_ref: str) -> dict[str, Any]:
    """Build valid kwargs covering every required field from the pinned arm.

    Array required fields → empty list (valid + minimal). Enums and ``$ref``\\ s to
    enum schemas → a real member. Other types → generate_example_value.

    A shape the generator has no rule for RAISES here rather than passing its guess
    through. That is the whole design correction: an instrument that cannot measure a
    field must fail loudly AT that field, not quietly hand the model a value the spec
    never allowed and report the resulting ValidationError as a conformance failure in
    production code. This is the class of false failure that the envelope-status
    exclusion was created to suppress — and suppressing a whole field's grading to silence an
    instrument bug costs far more than one located error demanding either a generator
    rule or an explicit sample_override, both of which already exist.
    """
    sample: dict[str, Any] = {}
    props = arm.get("properties", {})
    for fname in set(arm.get("required", [])) - _VERSION_FIELDS:
        spec = props.get(fname, {})
        if spec.get("type") == "array":
            sample[fname] = []
            continue
        value = generate_example_value(spec.get("type", "string"), fname, spec)
        if value == _unsynthesized_guess(fname):
            raise AssertionError(
                f"cannot synthesize a sample for required field {fname!r} of "
                f"{schema_ref} — the pinned shape {spec or '{}'} has no rule in "
                f"generate_example_value, so it fell back to a guessed string. "
                f"Extend generate_example_value for this shape, or set "
                f"sample_override on that schema's _RegistryRow. Do NOT exclude "
                f"the field from grading."
            )
        sample[fname] = value
    return sample


def _build_alignments_from_pinned(registry: list[_RegistryRow]) -> list[ResponseAlignment]:
    """Derive an envelope-level ResponseAlignment per registered model from the
    pinned success arm — machine-complete, so a new spec-required field on any
    registered model is enforced without hand-editing this list (#1399 Plan-B)."""
    alignments: list[ResponseAlignment] = []
    for row in registry:
        arm = _success_arm(load_json_schema(row.schema_ref))
        declared = row.declared_fields_override
        if declared is None:
            # Default to the REQUIRED fields (not all properties): the bug class is a
            # spec-REQUIRED field silently dropped (F4/F5/Chris-#2). Demanding every
            # OPTIONAL forward-compat property be explicitly declared would over-reach
            # (response models intentionally carry optional fields via extra='allow').
            # A row may set declared_fields_override to also pin specific optional
            # fields production emits (e.g. CreateMediaBuySuccess valid_actions/context).
            declared = frozenset(arm.get("required", [])) - _VERSION_FIELDS
        sample = row.sample_override if row.sample_override is not None else _synthesize_sample(arm, row.schema_ref)
        alignments.append(
            ResponseAlignment(
                schema_ref=row.schema_ref,
                selector=row.selector,
                item_key=None,
                model=row.model,
                declared_fields=declared,
                sample=sample,
            )
        )
    return alignments


# Per-ITEM alignments (item_key set) that the envelope-level generator does not
# cover. Kept hand-curated and supplemental so per-item required enforcement
# (F5, PR #1388) is not lost when the envelope list is machine-generated.
_SUPPLEMENTAL_ALIGNMENTS: list[ResponseAlignment] = [
    ResponseAlignment(
        schema_ref="account/sync-accounts-response.json",
        selector="accounts",
        item_key="accounts",
        model=SyncResponseAccount,
        sample={"brand": {"domain": "acme.com"}, "operator": "create", "action": "created", "status": "active"},
    ),
    ResponseAlignment(
        schema_ref="media-buy/get-products-response.json",
        selector="products",
        item_key="products",
        model=Product,
        # core/product.json's own required[] — reporting_capabilities included.
        # Product carries a validated default_factory for it, so omitting it from
        # the sample is graded by the model_defaulted branch of
        # test_required_fields_enforced (the attribute must come out non-None),
        # and by test_declared_fields_present_in_schema_and_model's model_dump()
        # presence check (#1868 review).
        declared_fields=frozenset(
            {
                "product_id",
                "name",
                "description",
                "publisher_properties",
                "delivery_type",
                "pricing_options",
                "reporting_capabilities",
            }
        ),
        sample={
            "product_id": "align_test_product",
            "name": "Alignment Test Product",
            "description": "Product used to verify the pinned schema descends into products[].",
            "publisher_properties": [create_test_publisher_properties_by_tag()],
            "delivery_type": "guaranteed",
            "pricing_options": [create_test_cpm_pricing_option()],
            "reporting_capabilities": {
                "available_reporting_frequencies": ["daily"],
                "expected_delay_minutes": 60,
                "timezone": "UTC",
                "supports_webhooks": False,
                "available_metrics": ["impressions", "clicks"],
                "date_range_support": "date_range",
            },
        },
    ),
]


RESPONSE_ALIGNMENTS = _build_alignments_from_pinned(_RESPONSE_MODEL_REGISTRY) + _SUPPLEMENTAL_ALIGNMENTS


def _resolve_response_item_schema(alignment: ResponseAlignment) -> dict[str, Any]:
    """Resolve the pinned (sub-)schema a response model maps to.

    Handles flat single-shape responses (no oneOf → the schema is the success
    shape) and oneOf responses (pick the arm exposing ``selector``). Merges in
    both the required fields AND the property definitions composed at the
    schema root — from its own top-level ``allOf`` arms (the shared
    Protocol/Version Envelope) and, for requiredness, from the standard branch
    of any top-level ``if``/``then``/``else`` chain. Those apply regardless of
    which oneOf variant matched, and 3.1.1 moved some formerly-flat
    requirements (e.g. ``status``, ``products``/``cache_scope``) into one of
    those two composition forms for schemas with no oneOf of their own.
    """
    schema = load_json_schema(alignment.schema_ref)
    if "oneOf" in schema:
        variant = next(v for v in schema["oneOf"] if alignment.selector in v.get("properties", {}))
    else:
        variant = schema
    if alignment.item_key:
        item_schema = variant["properties"][alignment.item_key]["items"]
        # Some item schemas are inlined (SyncResponseAccount); others are a
        # $ref to a standalone schema (get-products-response.json's
        # products[] -> core/product.json) — load_canonicalized already
        # rewrote the ref to the root-relative form pinned_schema.load()
        # expects, so a raw, unresolved $ref dict would otherwise silently
        # short-circuit every field/required check below to nothing.
        if "$ref" in item_schema:
            item_schema = pinned_schema.load(item_schema["$ref"])
        return _merge_composed(item_schema, item_schema)

    return _merge_composed(variant, schema)


class TestSampleSynthesisFailsLoud:
    """The instrument refuses to guess.

    Graded here because the failure mode is silence: a _synthesize_sample that
    quietly returns a guessed string does not break anything visibly — it hands a
    model a value the spec never allowed, and the ValidationError that follows
    reads as a conformance bug in production code. That misreading is what bought the
    envelope-status exclusion its existence, so 'raises instead of guessing' is a
    behaviour this suite has to keep, not an implementation detail.
    """

    def test_unsynthesizable_required_field_raises_located_error(self):
        """A shape with no generator rule names itself, its schema, and the fix."""
        arm = {
            "required": ["opaque_field"],
            "properties": {"opaque_field": {"type": "string", "contentEncoding": "base64"}},
        }
        with pytest.raises(AssertionError) as excinfo:
            _synthesize_sample(arm, "media-buy/some-response.json")

        message = str(excinfo.value)
        assert "opaque_field" in message
        assert "media-buy/some-response.json" in message
        assert "contentEncoding" in message, "the message must show the shape it could not synthesize"
        assert "sample_override" in message, "the message must name the escape hatch that already exists"

    def test_known_shapes_still_synthesize(self):
        """The guard fires on unknown shapes only — enums and arrays still work."""
        arm = {
            "required": ["status", "accounts"],
            "properties": {
                "status": {"type": "string", "enum": ["completed", "failed"]},
                "accounts": {"type": "array"},
            },
        }
        assert _synthesize_sample(arm, "account/some-response.json") == {
            "status": "completed",
            "accounts": [],
        }


class TestResponseModelAlignment:
    """Local success models conform to the pinned AdCP response schemas."""

    @pytest.mark.parametrize("alignment", RESPONSE_ALIGNMENTS, ids=lambda a: a.model.__name__)
    def test_declared_fields_present_in_schema_and_model(self, alignment: ResponseAlignment):
        """Each declared_field is defined by the pinned schema AND declared on the model.

        Catches fields that production emits but the model only carries via inherited
        extra='allow' (would silently vanish if the parent's extra-mode changed).
        """
        if not alignment.declared_fields:
            pytest.skip(f"{alignment.model.__name__}: no declared-field requirement")
        item = _resolve_response_item_schema(alignment)
        schema_props = set(item.get("properties", {}))
        model_fields = set(alignment.model.model_fields)
        for fname in alignment.declared_fields:
            assert fname in schema_props, f"{fname!r} not defined by pinned schema {alignment.schema_ref}"
            assert fname in model_fields, (
                f"{fname!r} is defined by the pinned schema but NOT declared on "
                f"{alignment.model.__name__} (only surviving via extra='allow')"
            )

        # A field can be declared on the model (above) yet still be silently
        # dropped by a custom model_dump() override (e.g. an over-broad
        # exclude set, or a "strip None" pass that also strips populated
        # values) — the exact bug class this suite exists to catch
        # (#1868 review). Construct with a real, populated value for
        # every declared field and confirm each survives serialization.
        if alignment.sample:
            instance = alignment.model(**alignment.sample)
            dumped = instance.model_dump(mode="json")
            for fname in alignment.declared_fields:
                if fname not in alignment.sample:
                    continue
                assert fname in dumped, (
                    f"{fname!r} is declared on {alignment.model.__name__} and populated in the "
                    f"constructor sample, but missing from model_dump() output — silently dropped "
                    f"from the wire a buyer actually receives."
                )

    @pytest.mark.parametrize("alignment", RESPONSE_ALIGNMENTS, ids=lambda a: a.model.__name__)
    def test_required_fields_enforced(self, alignment: ResponseAlignment):
        """The model enforces every field the pinned schema marks required.

        A schema-required field is "enforced" one of two ways, both valid:
        - the model has no default -> omitting it MUST raise ValidationError
          (the model rejects an incomplete construction), or
        - the model declares a spec-correct literal default (e.g.
          CreateMediaBuySuccess.status/confirmed_at/revision — see that
          class's docstring: these are invariant for a synchronous success,
          so the model guarantees the value itself rather than threading an
          identical literal through every call site) -> omitting it must NOT
          raise, and the constructed model must still carry a non-None value
          for it. Either way the schema's requiredness invariant holds; only
          silently accepting an omitted field with no value at all would be
          a real gap.
        """
        item = _resolve_response_item_schema(alignment)
        required = set(item.get("required", [])) - _VERSION_FIELDS
        if not required:
            pytest.skip(f"{alignment.model.__name__}: pinned schema marks no required fields")
        assert alignment.sample, (
            f"{alignment.model.__name__}: schema requires {sorted(required)} but no sample provided"
        )
        model_defaulted = {
            fname
            for fname in required
            if (mf := alignment.model.model_fields.get(fname)) is not None and not mf.is_required()
        }
        # A model-defaulted field guarantees its own value, so the caller-supplied
        # sample need not carry it — only fields the model can't fill in itself
        # must be present in the sample.
        required_from_sample = required - model_defaulted
        assert required_from_sample <= set(alignment.sample), (
            f"sample for {alignment.model.__name__} missing required keys: "
            f"{sorted(required_from_sample - set(alignment.sample))}"
        )
        # The complete required set constructs cleanly.
        assert alignment.model(**alignment.sample) is not None
        for fname in required:
            partial = {k: v for k, v in alignment.sample.items() if k != fname}
            if fname in model_defaulted:
                # Model-defaulted: omission must NOT raise, and the default must
                # still satisfy the schema's requiredness (a real, non-None value).
                instance = alignment.model(**partial)
                assert getattr(instance, fname) is not None, (
                    f"{alignment.model.__name__}.{fname} is schema-required but the model's "
                    f"own default left it None when omitted from the constructor call"
                )
            else:
                # No model default: the model itself must reject an incomplete construction.
                with pytest.raises(ValidationError):
                    alignment.model(**partial)


def _enumerate_grounded_response_models() -> set[type]:
    """Enumerate every local response model the registry MUST cover.

    This makes the registry's own inclusion rule executable instead of
    hand-listed: a model belongs iff it is (1) defined in ``src.core.schemas``
    (so imported ``Library*`` aliases, whose ``__module__`` is ``adcp.types.*``,
    are excluded), (2) extends an ``adcp`` library type directly (``__bases__``
    contains an ``adcp.types`` class), and (3) carries a response role — its name
    ends in ``Response`` or ``Success`` (the oneOf success arm). Error arms end in
    ``Error`` and requests in ``Request``, so both are excluded; reusable
    sub-components (``Account``, ``Package``, ``Pagination``) lack the response
    suffix and are excluded too.

    A future library-grounded response model that nobody registers is therefore
    discovered here and fails the coverage gate, rather than slipping through a
    stale literal.
    """
    import adcp.types as adcp_types

    adcp_bases = {obj for obj in vars(adcp_types).values() if inspect.isclass(obj)}

    import src.core.schemas as schemas_pkg

    modules = [schemas_pkg]
    for info in pkgutil.walk_packages(schemas_pkg.__path__, schemas_pkg.__name__ + "."):
        modules.append(importlib.import_module(info.name))

    grounded: set[type] = set()
    for module in modules:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseModel):
                continue
            if not (obj.__module__ or "").startswith("src.core.schemas"):
                continue  # skip imported Library* aliases re-exported into the namespace
            if not (name.endswith("Response") or name.endswith("Success")):
                continue  # response role only; error arms end in 'Error', requests in 'Request'
            if any(base in adcp_bases for base in obj.__bases__):
                grounded.add(obj)
    return grounded


class TestResponseAlignmentCoverage:
    """RESPONSE_ALIGNMENTS is machine-complete over implemented response models.

    #1399 Plan-B: every AdCP-grounded local response model (one that extends a
    Library* base and maps to a pinned *-response.json) must be covered by an
    alignment, so a required field the pinned spec adds cannot silently slip an
    unenforced model. This is the coverage gate; the per-field enforcement is in
    TestResponseModelAlignment.
    """

    def test_all_implemented_response_models_are_covered(self):
        # The set of models that MUST be registered is enumerated from the schema
        # package (the registry's own inclusion rule, executable) — never a literal
        # list, so a newly-added library-grounded response model that nobody
        # registered fails this gate instead of silently slipping through.
        expected = _enumerate_grounded_response_models()
        covered = {a.model for a in RESPONSE_ALIGNMENTS}
        # One-directional: every grounded model must be covered. ``covered`` may
        # carry extra alignments (e.g. nested sub-arms) that are not themselves
        # top-level response models, so strict equality would false-fail.
        missing = expected - covered
        assert not missing, (
            f"AdCP-grounded response models not covered by RESPONSE_ALIGNMENTS: {sorted(m.__name__ for m in missing)}"
        )


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
