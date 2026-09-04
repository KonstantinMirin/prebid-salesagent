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
import typing
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.core.exceptions import AdCPInvalidRequestError
from src.core.schemas import (
    CreateMediaBuyRequest,
    CreateMediaBuySuccess,
    GetProductsRequest,
    GetSignalsResponse,
    Product,
    Signal,
    SyncAccountsResponse,
    SyncResponseAccount,
    UpdateMediaBuySuccess,
)
from src.core.schemas.delivery import GetCreativeDeliveryResponse
from tests.helpers import pinned_schema
from tests.helpers.adcp_factories import create_test_cpm_pricing_option, create_test_publisher_properties_by_tag
from tests.helpers.registered_tools import registered_tool_shapes
from tests.helpers.request_schemas import (
    graded_request_schemas,
    pinned_request_schema_candidates,
)

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

#: ``(schema ref, request DTO)`` for every registered tool the pinned tree grades.
#:
#: Was ``SCHEMA_TO_MODEL_MAP``, six hand-written rows of schema -> model, and it is worth
#: recording what the six were: five live, and ``CreateMediaBuyRequest`` COMMENTED OUT
#: since 52dc23104 "pending brand_card implementation". That is what a hand-written
#: membership list buys — the ability to remove one model from the grading with a ``#``
#: and leave the suite green. A real schema deviation went ungraded for months behind
#: that character, which is the same failure the request-factory suite's own table
#: produced for ``list_accounts``.
#:
#: The rationale was not merely stale, it was FALSE at the pin: measured at adcp 6.6.0 /
#: AdCP 3.1.1, ``create-media-buy-request.json`` declares no ``brand_card`` property at
#: all (its brand-ish property is ``brand``, which the model has), and ``account`` is in
#: ``/required`` and required on the model. What actually kept the model out was a bug in
#: the synthetic generator below, which read ``loc[0]`` on NESTED ``extra_forbidden``
#: errors and so blamed the model for sub-keys the generator itself invented. So the
#: exclusion outlived not just its urgency but its premise, and the instrument that
#: created it was reporting a production defect that did not exist.
#:
#: Membership now comes from the LIVE MCP registry via ``graded_request_schemas()``: a
#: tool is graded because it is registered and its DTO resolves a pinned schema, and
#: there is no key set to omit it from. It grades thirteen models where the table graded
#: five, and CreateMediaBuyRequest is among them again.
#:
#: Built at import, which is what a ``parametrize`` argument has to be — so collecting
#: this module registers the MCP server. That is the cost of reading membership from the
#: registry rather than restating it, and it is the cost the ticket is buying.
REQUEST_SCHEMA_PARAMS = [
    pytest.param(schema_ref, model_class, id=tool_name)
    for tool_name, (schema_ref, model_class) in sorted(graded_request_schemas().items())
]

# Version metadata fields present in AdCP JSON schemas that models don't declare explicitly.
# These have defaults or are managed by the library base class — exclude from all comparisons.
_VERSION_FIELDS: frozenset[str] = frozenset({"adcp_version", "adcp_major_version"})

# Fields the SDK's current schema tree defines but the local model does not yet
# model. These are spec-vs-library mismatches, not bugs in our code.
#
# Keys are schema refs as `pinned_request_schema_ref` derives them;
# `KNOWN_SCHEMA_LIBRARY_MISMATCHES.get(schema_ref, set())` lookups silently fall back
# to an empty set otherwise. get-products drift is tracked in #1308: the live AdCP schema
# carries `if_catalog_version`/`if_pricing_version`, which the pinned library does not
# model yet (`adcp_major_version` is covered by `_VERSION_FIELDS` instead).
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


class _CannotSynthesize(AssertionError):
    """The generator has no rule for a pinned shape and refuses to invent one.

    Raised only under ``strict`` (the response side). The lenient default keeps the
    pre-existing request-side behaviour byte-for-byte, so adding this cannot quietly
    become a rewrite of the generator.

    Subclasses ``AssertionError`` so an escaping instance reads as a test-instrument
    failure rather than a production defect — which is the entire point. An invented
    value is not neutral: fed to a required enum or formatted field it raises
    ``ValidationError``, and the alignment suite then reports the instrument's own gap
    as a conformance failure against production code. That is the story
    ``_unsynthesized_guess`` tells about ``test_status_value``, and it is what bought
    the envelope's ``status`` its blanket exclusion from requiredness grading — the
    exclusion GH #1900 exists to undo.
    """


def _cannot_synthesize(field_type: str, field_name: str, field_spec: dict | None, reason: str) -> _CannotSynthesize:
    """Build the located refusal, naming the shape and the two sanctioned escapes."""
    return _CannotSynthesize(
        f"cannot synthesize a value for {field_name or '<unnamed>'} (type {field_type!r}): {reason}. "
        f"Pinned shape: {field_spec if field_spec else '{}'}. Extend generate_example_value for this "
        f"shape, or set sample_override on the schema's _RegistryRow. Do NOT exclude the field from "
        f"grading — suppressing a field to silence an instrument gap is the defect this raise exists "
        f"to prevent."
    )


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


def _pad_to_min_length(value: str, field_spec: dict | None) -> str:
    """Grow *value* to the pin's ``minLength``, padding with a character its pattern admits.

    The naming and pattern rules above produce SHORT readable values, and some pinned
    strings want a long one: ``idempotency_key`` is
    ``^[A-Za-z0-9_.:-]{16,255}$``, so ``"test_value"`` matches the character class and
    fails the length. Without this the generator hands a value the pin itself would
    reject to a model that correctly rejects it, and the suite reports the instrument's
    gap as a production defect — the failure mode ``_CannotSynthesize`` documents.

    Pads with ``"0"``: every pattern branch that reaches here matched on ``a-z0-9``, so
    the class admits digits and lengthening cannot invalidate the pattern that selected
    the value. KNOWN CEILING — this is length only. A pin that constrains STRUCTURE
    beyond a character class (a UUID shape, a prefix) still needs its own rule above.
    """
    minimum = (field_spec or {}).get("minLength", 0)
    return value if len(value) >= minimum else value + "0" * (minimum - len(value))


#: Substring of a field's NAME -> the example value that name implies. A naming
#: heuristic, not a reading of the pin: it is what the generator falls back on when the
#: schema states no enum, const or pattern to derive from. Ordered — the first match
#: wins, so "date" is tested before "time" ("start_date" must not become a datetime).
_STRING_BY_FIELD_NAME: tuple[tuple[str, str], ...] = (
    ("date", "2025-02-01"),
    ("time", "2025-02-01T00:00:00Z"),
    ("url", "https://example.com/test"),
    ("email", "test@example.com"),
    ("version", "1.0.0"),
    ("offering", "Nike Air Jordan 2025 basketball shoes"),
    ("po_number", "PO-TEST-12345"),
)


def _example_string(field_name: str, field_spec: dict | None) -> str | None:
    """A string satisfying *field_spec*, or None when no rule matches.

    Returns rather than raises so the ONE caller owns both the strict refusal and the
    minLength padding; every rule used to return directly, and each new constraint had
    to be remembered at eight exits.
    """
    pattern = (field_spec or {}).get("pattern")
    if pattern:
        if pattern == r"^\d{4}-\d{2}-\d{2}$":
            return "2025-02-01"
        # Domain patterns (lowercase alphanumeric + hyphens + dots).
        if "a-z0-9" in pattern and "\\." in pattern:
            return "example.com"
        # Lowercase identifier patterns (e.g. brand_id: ^[a-z0-9_]+$).
        if "a-z0-9" in pattern:
            return "test_value"
    for fragment, value in _STRING_BY_FIELD_NAME:
        if fragment in field_name.lower():
            return value
    # Checked after the table so a name like "valid_id" cannot capture "date"/"time".
    if "id" in field_name.lower():
        return f"test_{field_name}_123"
    return None


def _unambiguous_arms(arms: list[Any]) -> list[Any]:
    """*arms* minus those whose value would ALSO satisfy a broader sibling.

    ``oneOf`` means exactly one arm matches, so an arm that narrows a sibling by
    ``const``/``enum`` is a trap for a generator: its value matches the narrow arm AND
    the broad one, and the instance fails validation for matching twice.
    ``core/start-timing.json`` is the live case — ``{const: "asap"}`` beside
    ``{type: string, format: date-time}`` — and because this repo's validator asserts no
    date-time format checker, EVERY string satisfies the second arm. Picking "asap"
    yields a payload the pin rejects; picking a timestamp matches only the second.
    ``CreateMediaBuyRequestFactory`` already documents the same reasoning for the same
    field, reached by hand.

    KNOWN CEILING: overlap is judged on ``type`` alone. Two arms that overlap through
    ranges, patterns or object shapes are not detected, and the first is taken. Widen
    this when a pinned schema actually needs it, not before — the alternative is
    synthesizing a candidate per arm and validating each, which costs a validator per
    node for a case the pin does not yet contain.
    """
    broad_types = {
        arm.get("type") for arm in arms if isinstance(arm, dict) and "const" not in arm and "enum" not in arm
    }
    unambiguous = [
        arm
        for arm in arms
        if not (isinstance(arm, dict) and ("const" in arm or "enum" in arm) and arm.get("type") in broad_types)
    ]
    return unambiguous or arms


def _first_disjunct(node: dict[str, Any]) -> dict[str, Any]:
    """Fold the FIRST arm of a root ``oneOf``/``anyOf`` into *node*.

    A disjunctive schema states "an instance looks like ONE of these", so a synthesizer
    has to CHOOSE an arm; reading only the root leaves ``properties`` and ``required``
    empty and yields ``{}``. ``core/account-ref.json`` is the live case — a bare
    ``type: object`` whose whole shape lives in two ``oneOf`` arms (account_id, or
    brand+operator) — and ``{}`` is what made three tools skip while reporting that the
    SPEC does not require ``account``, which it does.

    First arm, not a search for one that validates: the choice has to be deterministic
    or the generated payload changes between runs. Arms are ordered in the pin and the
    first is the canonical spelling — except where taking it would produce a value that
    satisfies TWO arms, which ``oneOf`` (exactly one) rejects. See
    :func:`_unambiguous_arms`.
    """
    for keyword in ("oneOf", "anyOf"):
        arms = node.get(keyword)
        if not arms:
            continue
        arms = _unambiguous_arms(arms)
        arm = pinned_schema.load_canonicalized(arms[0]["$ref"]) if "$ref" in arms[0] else arms[0]
        rest = {key: value for key, value in node.items() if key != keyword}
        return {
            **rest,
            **arm,
            "properties": {**rest.get("properties", {}), **arm.get("properties", {})},
            "required": sorted(set(rest.get("required", [])) | set(arm.get("required", []))),
        }
    return node


def _derived_pinned_shape(node: dict[str, Any]) -> dict[str, Any]:
    """*node* with its composition folded in: ``allOf`` arms merged, one disjunct chosen.

    The whole point of the instrument is that the shape comes from the PIN. A node whose
    shape is composed rather than declared inline reads as empty otherwise, and an empty
    read is indistinguishable from "the pin declares nothing" — which is how invented
    shapes got hardcoded here in the first place.

    ``_merge_composed`` is the response side's allOf/if-then-else merge, shared rather
    than reimplemented: there is one rule for what a composed pinned node's fields are.
    """
    return _first_disjunct(_merge_composed(node, node))


def generate_example_value(
    field_type: str, field_name: str = "", field_spec: dict = None, *, strict: bool = False
) -> Any:
    """Generate a reasonable example value for a JSON schema type.

    ``strict`` is the response side's contract: a shape with no rule raises
    :class:`_CannotSynthesize` instead of inventing a value. The default stays lenient
    so pre-existing request-side callers are unchanged byte-for-byte.
    """
    # Inline enum (e.g. cache_scope: {"type": "string", "enum": ["public", "account"]}):
    # a generic "test_<field>_value" string is not a member of the enum and fails
    # Pydantic validation on construction — checked before the $ref/oneOf/allOf
    # branches below since an inline enum can appear on any of those field shapes.
    if field_spec and "enum" in field_spec:
        return field_spec["enum"][0]

    # ``const`` is a one-member enum and the pin uses it for oneOf DISCRIMINATORS —
    # core/signal-id.json fixes ``source`` at "catalog" on one arm and "agent" on the
    # other. Reading enum but not const means the generator invents a value for the one
    # field whose value the pin states outright, and the arm it just chose is then
    # discriminated to the wrong branch. Handling oneOf without handling const is half
    # a fix, because const is how a oneOf says which arm you are on.
    if field_spec and "const" in field_spec:
        return field_spec["const"]

    # Handle $ref fields (complex nested objects). DERIVED FROM THE PIN, never from a
    # table of shapes keyed on the ref's spelling. Fifteen such shapes used to sit here
    # — budget, package, brand-manifest, reporting-webhook, context, ext and the rest —
    # each matched by substring against the ref path and each frozen on the day it was
    # written. A shape that does not move with the pin is not a sample of the pinned
    # schema, it is an assertion about it, and when the two disagree the suite reports
    # the disagreement AGAINST PRODUCTION: that is how CreateMediaBuyRequest came to be
    # excluded from the alignment guard for six months over `total_budget`, a field the
    # model gets exactly right.
    if field_spec and "$ref" in field_spec:
        ref = field_spec["$ref"]
        try:
            ref_schema = _derived_pinned_shape(load_json_schema(ref))
            if "enum" in ref_schema:
                return ref_schema["enum"][0]
            ref_type = ref_schema.get("type", "object")
            if ref_type != "object":
                return generate_example_value(ref_type, field_name, ref_schema, strict=strict)
            # Generate object with required fields from the resolved schema
            obj = {}
            required_fields = ref_schema.get("required", [])
            for prop_name, prop_spec in ref_schema.get("properties", {}).items():
                if prop_name in required_fields:
                    prop_type = prop_spec.get("type", "string")
                    obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec, strict=strict)
            if obj or not required_fields:
                # No required properties is a real answer, not a failure to read one: a
                # pinned object that requires nothing is satisfied by {}. Returning it
                # is derived; what must not happen is returning {} because the shape
                # was UNREADABLE, which the composition merge above now prevents.
                return obj
            if strict:
                raise _cannot_synthesize(
                    field_type, field_name, field_spec, f"resolved $ref {ref!r} exposes no readable required properties"
                )
            return {}
        except _CannotSynthesize:
            raise
        except Exception as exc:
            if strict:
                raise _cannot_synthesize(
                    field_type, field_name, field_spec, f"$ref {ref!r} could not be resolved"
                ) from exc
            return {}

    # Handle allOf with $ref (e.g., time_budget: allOf[{$ref: duration.json}])
    if field_spec and "allOf" in field_spec:
        for variant in field_spec["allOf"]:
            if "$ref" in variant:
                return generate_example_value("object", field_name, variant, strict=strict)
        # If no $ref in allOf, merge properties from all variants
        merged_spec = dict(field_spec)
        del merged_spec["allOf"]
        for variant in field_spec["allOf"]:
            merged_spec.update(variant)
        return generate_example_value(merged_spec.get("type", "object"), field_name, merged_spec, strict=strict)

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
            return generate_example_value(variant_type, field_name, ref_schema, strict=strict)
        variant_type = first_variant.get("type", "string")
        return generate_example_value(variant_type, field_name, first_variant, strict=strict)

    if field_type == "string":
        matched = _example_string(field_name, field_spec)
        if matched is None:
            if strict:
                # Reached recursively for a container's property too, where the guess is
                # embedded in the returned object and _synthesize_sample's top-level
                # sentinel check never sees it.
                raise _cannot_synthesize(field_type, field_name, field_spec, "no naming or pattern rule matched")
            matched = _unsynthesized_guess(field_name)
        # ONE exit, so the pin's minLength is honoured whichever rule produced the value.
        # It used to be applied on the pattern branch alone, and `credentials` — pinned
        # minLength 32 with no pattern — came back as a 22-character guess that the pin
        # itself rejects. A sample the pin would reject cannot grade whether a model
        # accepts pinned samples.
        return _pad_to_min_length(matched, field_spec)
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
                        # The shared factory owns this shape, so the generator cannot drift
                        # from it. Inlining a sample here is what let the old one keep saying
                        # "format": "display_300x250" and omitting the spec-required assets --
                        # retired 2.x vocabulary that validated only while the request field
                        # pointed at the list_creatives RESPONSE model. A generator emitting
                        # non-spec fields cannot grade whether a model accepts spec fields,
                        # which is this test's whole purpose.
                        from tests.factories.creative_asset import make_creative_asset_request

                        return [make_creative_asset_request()]
                    # The ELEMENT is generated by the same $ref rule as any other value,
                    # rather than by a second resolver that reads less. The old one gave
                    # up on an object-typed item and returned [{}] — an invented element
                    # for a shape the pin describes in full — which is why the generated
                    # create_media_buy carried `packages: [{}]` and the suite then read
                    # the model's correct refusal of it as a conformance failure.
                    item = generate_example_value(
                        items_spec.get("type", "object"), field_name, items_spec, strict=strict
                    )
                    # ``{}`` is the ONE result that means "read nothing": every other
                    # value, falsy ones included (0, "", []), is what the pin declares.
                    if item != {}:
                        return [item]
                    if strict:
                        raise _cannot_synthesize(
                            field_type, field_name, field_spec, f"array items $ref {ref!r} resolves to an unread object"
                        )
                    return [item]

                item_type = items_spec.get("type", "string")
                if item_type == "object":
                    # Composition folded in first, same as every other object: an INLINE
                    # item schema can be a discriminated oneOf too. get-products' `refine`
                    # is one — its properties live entirely in the arms — so reading only
                    # the top level produced [] against a pinned minItems of 1.
                    items_spec = _derived_pinned_shape(items_spec)
                    # Generate a proper object with required fields
                    obj = {}
                    if "properties" in items_spec:
                        required_fields = items_spec.get("required", [])
                        for prop_name, prop_spec in items_spec["properties"].items():
                            if prop_name in required_fields or "id" in prop_name:
                                prop_type = prop_spec.get("type", "string")
                                obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec, strict=strict)
                    if obj:
                        return [obj]
                    # Empty half only: no required/id property was readable, so [] here is an
                    # invented element shape — unlike a top-level required array, whose empty
                    # list is a spec-valid derived minimal instance (minItems is absent).
                    if strict:
                        raise _cannot_synthesize(
                            field_type,
                            field_name,
                            field_spec,
                            "array items object exposes no readable required properties",
                        )
                    return []
                else:
                    # Generate one example item
                    return [generate_example_value(item_type, field_name, items_spec, strict=strict)]
        # 'items' is absent, or is a LIST (tuple validation) the branch above cannot read,
        # so the element shape is unknown and [] would be invented.
        if strict:
            raise _cannot_synthesize(field_type, field_name, field_spec, "array has no readable 'items' schema")
        return []
    elif field_type == "object":
        # Two shapes keyed on the FIELD NAME used to sit here — {total, currency, pacing}
        # for anything named *budget*, {geo_countries: [US]} for anything named
        # *targeting* — and they returned BEFORE the derivation below, so they shadowed
        # the pinned schema even when it was perfectly readable. That is strictly worse
        # than the ref-keyed table: `total_budget` is an INLINE object whose pinned
        # properties are {amount, currency}, both required, and our model declares
        # exactly those — yet the generator emitted `total`/`pacing`, the model
        # correctly rejected them, and the suite read that as the MODEL rejecting spec
        # fields. Derived from the pin now, like everything else.
        spec = _derived_pinned_shape(field_spec) if field_spec else None
        if spec and "properties" in spec:
            # Generate a minimal object with required fields
            obj = {}
            required_fields = spec.get("required", [])
            for prop_name, prop_spec in spec["properties"].items():
                if prop_name in required_fields:
                    prop_type = prop_spec.get("type", "string")
                    obj[prop_name] = generate_example_value(prop_type, prop_name, prop_spec, strict=strict)
            return obj
        if strict:
            raise _cannot_synthesize(
                field_type, field_name, field_spec, "object declares no 'properties' to derive from"
            )
        return {}
    else:
        if strict:
            raise _cannot_synthesize(field_type, field_name, field_spec, f"no branch handles type {field_type!r}")
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
        REQUEST_SCHEMA_PARAMS,
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
            # Extract which fields were rejected. TOP-LEVEL only: a nested
            # ``extra_forbidden`` (loc ``("total_budget", "total")``) is the GENERATOR
            # inventing a sub-key the pinned $ref does not declare, not the model
            # rejecting a spec field. Reading ``loc[0]`` regardless reported
            # ``total_budget`` as rejected while CreateMediaBuyRequest accepts it —
            # the instrument's gap dressed as a production defect, which is what
            # ``_CannotSynthesize`` exists to keep out of this suite.
            rejected_fields = [
                err["loc"][0] for err in e.errors() if err["type"] == "extra_forbidden" and len(err["loc"]) == 1
            ]
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

    @pytest.mark.parametrize("schema_ref,model_class", REQUEST_SCHEMA_PARAMS)
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
                    # FAIL, not skip. The two lines above already say "Only fail if model
                    # requires FEWER fields than spec" -- and this branch is exactly that
                    # case, so skipping here contradicted the guard's own stated rule and
                    # made it report green on the one thing it exists to catch. It hid two
                    # real violations (SyncCreativesRequest and UpdateMediaBuyRequest both
                    # relaxed the spec-required idempotency_key and account) behind the words
                    # "may be intentional for flexibility" -- an assumption, not a finding.
                    pytest.fail(
                        f"{model_class.__name__} makes these OPTIONAL where the pinned schema "
                        f"marks them REQUIRED: {sorted(not_enforced)}. Relaxing a required "
                        f"field silently accepts non-conformant requests; if the field is "
                        f"genuinely supplied at the boundary, supply it there rather than "
                        f"making the contract optional."
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

    @pytest.mark.parametrize("schema_ref,model_class", REQUEST_SCHEMA_PARAMS)
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
            account={"account_id": "acct_test"},
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
        REQUEST_SCHEMA_PARAMS,
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


class TestTheGeneratorAgreesWithThePin:
    """The instrument's own output, graded against the pin it claims to sample.

    Every other class here feeds a synthesized payload to a model and reports what the
    model does with it. NOTHING checked the payload itself, so an invalid sample was
    indistinguishable from a non-conformant model — and the suite reported the model.
    That is not hypothetical: the generator emitted ``total_budget: {total, currency,
    pacing}`` against a pin declaring ``{amount, currency}``, CreateMediaBuyRequest
    correctly refused it, the refusal read as "REJECTED AdCP spec fields", and the model
    was commented out of the alignment map on 2026-02-24 under a rationale about
    ``brand_card`` — a property the pin does not contain. It stayed out for six months
    and prkv.28 then missed a real deviation in a model nothing was grading.

    This is the check that makes the instrument accountable to the same artifact it
    grades production against. A rule that invents a shape now fails HERE, at the
    generator, instead of over there, as a false accusation.

    Scoped to the MINIMAL request: it is the payload built purely from ``/required``, so
    "the pin accepts it" is unambiguous. The FULL request deliberately carries every
    property at once, which a schema with if/then/else conditionals can reject for
    reasons that are not the generator's fault — see the module-level note on
    get-products' ``buying_mode``.
    """

    @pytest.mark.parametrize("tool_name", sorted(graded_request_schemas()))
    def test_the_minimal_request_is_one_the_pinned_schema_accepts(self, tool_name: str) -> None:
        schema_ref, _ = graded_request_schemas()[tool_name]
        payload = generate_minimal_valid_request(load_json_schema(schema_ref))

        violations = {
            ".".join(str(part) for part in error.absolute_path) or "<root>": error.message
            for error in pinned_schema.validator_for(schema_ref).iter_errors(payload)
        }

        assert not violations, (
            f"the generator's minimal {tool_name} request is not valid against {schema_ref}:\n"
            + "\n".join(f"  at {path}: {message}" for path, message in sorted(violations.items()))
            + "\n\nFix the GENERATOR, not the model. A sample the pin rejects cannot grade "
            "whether a model accepts pinned samples — it can only produce a false accusation."
        )

    @pytest.mark.parametrize("tool_name", sorted(graded_request_schemas()))
    def test_every_full_request_property_matches_its_own_pinned_subschema(self, tool_name: str) -> None:
        """Each generated property, graded against the pin's declaration OF THAT PROPERTY.

        This is the one that catches an invented SHAPE, and the minimal-request check
        above cannot: ``total_budget`` is not in create-media-buy's ``/required``, so the
        minimal payload never carries it and the six-month exclusion would have been
        reproduced under a green minimal check.

        Per-property rather than whole-document, deliberately. The full request carries
        every property AT ONCE, and a pinned schema may forbid exactly that:
        get-products' ``allOf`` states "if you send if_pricing_version then buying_mode
        must be 'wholesale'", so a document holding both is invalid for a reason that is
        the full-request STRATEGY's, not the generator's. Grading each value against
        ``properties[name]`` asks the question this test is actually about — is the shape
        the generator invented the shape the pin declares — and leaves document-level
        conditionals to the model, which is where they are enforced.
        """
        schema_ref, _ = graded_request_schemas()[tool_name]
        schema = load_json_schema(schema_ref)
        validator = pinned_schema.validator_for(schema_ref)
        declared = schema.get("properties", {})

        violations = {}
        for field, value in generate_full_valid_request(schema).items():
            if field not in declared:
                continue
            # Validated as a one-key document so the pin's own $ref resolution applies;
            # errors are then filtered to those rooted at this field, which drops the
            # document-level conditionals this test deliberately does not grade.
            for error in validator.iter_errors({field: value}):
                if error.absolute_path and error.absolute_path[0] == field:
                    violations[".".join(str(part) for part in error.absolute_path)] = error.message

        assert not violations, (
            f"the generator built {tool_name} properties that {schema_ref} does not "
            f"declare that way:\n"
            + "\n".join(f"  at {path}: {message}" for path, message in sorted(violations.items()))
            + "\n\nFix the GENERATOR. A value the pin rejects, handed to a model that "
            "correctly rejects it too, is reported by this suite as the MODEL rejecting a "
            "spec field — which is how CreateMediaBuyRequest left the guard for six months."
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
    #: A property identifying the success oneOf variant. ``None`` selects the arm by
    #: ``_success_shape``'s own rule, which is what every derived row uses; the
    #: supplemental per-item rows below name theirs.
    selector: str | None
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
    be synthesized generically -- it never weakens or skips a required field.
    ``declared_fields_override`` ADDS to the F4 declared-field check -- the pinned
    required set is always included -- so a row can also pin specific OPTIONAL fields
    production emits (e.g. CreateMediaBuySuccess valid_actions/context) without
    quietly dropping the required ones.

    ``selector`` is no longer carried: it named the property identifying the success
    ``oneOf`` arm, and every one of the twelve hand-written values was reproducible by
    ``_success_shape``'s no-selector rule -- verified arm-for-arm, byte-identical JSON,
    across the whole registry. A hand-written copy of a derivable fact is a place for
    the two to disagree, so the rows stopped carrying one. ``ResponseAlignment`` keeps
    the field for the supplemental per-item rows, which name it explicitly.
    """

    schema_ref: str
    model: type
    sample_override: dict[str, Any] | None = None
    declared_fields_override: frozenset[str] | None = None


@dataclass(frozen=True)
class _RowOverride:
    """The two per-row knobs, keyed by TOOL rather than restated beside a hand-written row."""

    sample: dict[str, Any] | None = None
    declared_fields: frozenset[str] | None = None


#: Per-tool overrides for the DERIVED rows. A tool appears here only when the generic
#: synthesizer cannot build a valid instance of a required field, or when production
#: emits an optional field worth pinning. It never weakens a required field.
_RESPONSE_OVERRIDES: dict[str, _RowOverride] = {
    "create_media_buy": _RowOverride(
        # packages requires the local package shape; synthesize is not reliable.
        # confirmed_at/revision carry NO model default any more (they are columns the
        # repository owns), so the sample has to supply them like any other
        # schema-required field the model will not fill in for itself.
        sample={
            "media_buy_id": "mb_1",
            "packages": [{"package_id": "pkg_1", "paused": False}],
            "confirmed_at": "2026-03-15T12:00:00Z",
            "revision": 1,
        },
        # Forward-compat fields production emits that must be explicitly declared (F4, PR #1388).
        declared_fields=frozenset({"valid_actions", "context"}),
    ),
    "get_media_buy_delivery": _RowOverride(
        sample={
            "reporting_period": {"start": "2025-02-01T00:00:00Z", "end": "2025-02-02T00:00:00Z"},
            "currency": "USD",
            "aggregated_totals": {"impressions": 0.0, "spend": 0.0, "media_buy_count": 0},
            "media_buy_deliveries": [],
        }
    ),
    "list_creatives": _RowOverride(
        sample={
            "query_summary": {"total_matching": 0, "returned": 0},
            "pagination": {"has_more": False},
            "creatives": [],
        }
    ),
    "get_adcp_capabilities": _RowOverride(
        # Newly graded by the derivation (it had no hand-written row). Two required
        # fields the generic synthesizer cannot derive: ``supported_protocols`` carries
        # ``minItems: 1``, so the "required array -> []" rule is not a spec-valid
        # instance here (the boundary
        # ``test_top_level_required_array_keeps_the_minimal_list_rule`` pins), and
        # ``adcp.idempotency`` is a nested oneOf object the string-by-field-name
        # heuristic turns into a string. Neither is a production defect.
        sample={
            "status": "completed",
            "adcp": {
                "major_versions": [3],
                "idempotency": {"supported": True, "replay_ttl_seconds": 86400},
            },
            "supported_protocols": ["media_buy"],
        }
    ),
}


#: Rows whose MODEL is spec-grounded but whose tool is NOT registered on the MCP
#: server, so the live-registry derivation cannot reach them. Both were graded before
#: the derivation landed and stay graded: dropping them would be a silent loss of
#: coverage, which is the failure this whole file exists to prevent.
#:
#: This list is the measured drift, not a design: the hand-written registry had rows
#: for two tools that are not registered AND no rows for three that are, so it had
#: drifted in BOTH directions at once. Derivation fixes one direction; this fixes the
#: other by naming it.
_UNREGISTERED_RESPONSE_ROWS: list[_RegistryRow] = [
    _RegistryRow(
        schema_ref="creative/get-creative-delivery-response.json",
        model=GetCreativeDeliveryResponse,
        sample_override={
            "reporting_period": {"start": "2025-02-01T00:00:00Z", "end": "2025-02-02T00:00:00Z"},
            "currency": "USD",
            "creatives": [],
        },
    ),
    _RegistryRow(schema_ref="signals/get-signals-response.json", model=GetSignalsResponse),
]


def _resolved_allof_arms(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each arm of a schema's top-level ``allOf``, ``$ref``s resolved.

    Requiredness and definedness are harvested from these same arms by
    ``_allof_required_fields`` and ``_allof_properties``. They walked the list
    independently before, which is the shape that lets the two halves drift apart —
    and they must not, because a field pulled out of an arm's ``required`` without
    that arm's ``properties`` is reported as schema-required and undefined in the
    same breath.
    """
    for arm in schema.get("allOf", []) or []:
        yield pinned_schema.load_canonicalized(arm["$ref"]) if "$ref" in arm else arm


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
    return {field for arm in _resolved_allof_arms(schema) for field in arm.get("required", [])}


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
    # Later arms win on key collision, which is what the sequential ``|=`` did.
    return {name: spec for arm in _resolved_allof_arms(schema) for name, spec in arm.get("properties", {}).items()}


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


def _success_shape(
    schema: dict[str, Any],
    *,
    selector: str | None = None,
    item_key: str | None = None,
) -> dict[str, Any]:
    """The pinned success (sub-)schema a response model maps to.

    ONE resolver, because there were two and they disagreed on the step that
    matters. Both picked a success arm out of a ``oneOf``; only one then merged the
    composition at the schema ROOT — the shared Protocol/Version Envelope arms and
    the standard branch of any top-level ``if``/``then``/``else`` — into it. The
    other returned the arm raw.

    That difference is not cosmetic: AdCP 3.1.1 composes ``status`` onto responses
    through a top-level ``allOf``, so for a ``oneOf`` response the un-merged
    resolver produced an arm with no ``status`` in ``properties`` at all. Every
    check keyed off "the fields this schema declares" — declared_fields, the
    sample, and the model_dump-survival check written for exactly the
    ``confirmed_at`` bug class — then skipped ``status`` silently, on the two models
    where it was most worth grading.

    Arm selection has two modes, and they are the reason the resolvers were
    separate:
    * ``selector`` — pick the arm exposing that property (the registry knows which
      field identifies its success arm);
    * no selector — pick the first arm whose ``required`` names neither ``errors``
      nor ``task_id``, i.e. is neither the error nor the submitted arm.
    Both then merge the root composition, which is the part that must not differ.

    ``item_key`` descends into an array's item schema (following a ``$ref`` to a
    standalone schema when the item is not inlined) and merges composition there.
    """
    if "oneOf" in schema:
        if selector is not None:
            variant = next(v for v in schema["oneOf"] if selector in v.get("properties", {}))
        else:
            variant = next(
                (arm for arm in schema["oneOf"] if not ({"errors", "task_id"} & set(arm.get("required", [])))),
                None,
            )
            if variant is None:
                raise AssertionError(
                    f"No success arm found in oneOf (all arms look like error/submitted): {schema.get('$id')}"
                )
    else:
        variant = schema

    if item_key:
        item_schema = variant["properties"][item_key]["items"]
        # Some item schemas are inlined (SyncResponseAccount); others are a $ref to a
        # standalone schema (get-products-response.json's products[] ->
        # core/product.json). load_canonicalized already rewrote the ref to the
        # root-relative form pinned_schema.load() expects, so a raw unresolved $ref
        # dict would silently short-circuit every field/required check below.
        if "$ref" in item_schema:
            item_schema = pinned_schema.load(item_schema["$ref"])
        return _merge_composed(item_schema, item_schema)

    return _merge_composed(variant, schema)


def _model_literal_value(model: type | None, fname: str) -> Any:
    """The single value *model* narrows ``fname`` to, or ``None``.

    A response type that only ever represents one outcome may narrow a spec enum to
    one member — ``CompletedTaskStatusMixin`` pins ``status`` to ``"completed"``
    because the model is the synchronous-success arm. The schema still lists the whole
    enum, so a sample synthesized from the schema alone can pick a DIFFERENT member
    and then fail to construct the model.

    That failure would be reported as a conformance defect while being an artefact of
    the instrument — the exact false-failure class this module refuses to tolerate
    elsewhere. The narrowing itself is not waved through: the caller asserts the
    narrowed value is a member of the schema's enum, so a model that narrows to
    something the spec does not allow still fails, and fails AT that field.
    """
    from typing import Literal, get_args, get_origin

    if model is None:
        return None
    field = model.model_fields.get(fname)
    if field is None or get_origin(field.annotation) is not Literal:
        return None
    args = get_args(field.annotation)
    return args[0] if len(args) == 1 else None


def _synthesize_sample(arm: dict[str, Any], schema_ref: str, model: type | None = None) -> dict[str, Any]:
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
        narrowed = _model_literal_value(model, fname)
        if narrowed is not None:
            allowed = spec.get("enum")
            assert allowed is None or narrowed in allowed, (
                f"{model.__name__}.{fname} narrows to {narrowed!r}, which the pinned "
                f"{schema_ref} does not allow (enum: {allowed})"
            )
            sample[fname] = narrowed
            continue
        if spec.get("type") == "array":
            sample[fname] = []
            continue
        try:
            value = generate_example_value(spec.get("type", "string"), fname, spec, strict=True)
        except _CannotSynthesize as exc:
            # The generator refuses at the field; only this frame knows WHICH schema was
            # being synthesized, so the located error is completed here. Previously this
            # was a post-hoc comparison against the guess sentinel, which could only
            # catch a guess returned at the TOP level — a guess embedded inside a
            # container came back as a well-formed dict and passed.
            raise _CannotSynthesize(
                f"cannot synthesize a sample for required field {fname!r} of {schema_ref} — {exc}"
            ) from exc
        sample[fname] = value
    return sample


#: Registered tools whose RESPONSE the pinned tree grades but production cannot satisfy,
#: as ``tool -> issue + what is absent``. SHRINK-ONLY: a row leaves when the response is
#: fixed, and nothing may be added without an issue naming the gap. This is the same
#: bargain as the deliver_* allowlist -- the gap stays ATTRIBUTABLE instead of hidden by
#: leaving the tool out of the grading, which is exactly how these two went unnoticed.
#:
#: ``test_known_response_gaps_are_still_real`` re-measures every row on every run, so a
#: row cannot outlive its defect the way a written rationale can.
_UNGRADED_RESPONSES: dict[str, str] = {
    "list_tasks": (
        "FIXME(#2201): the wire is {tasks, total, offset, limit, has_more} -- absent are "
        "top-level query_summary/pagination/status and, per tasks[] item, task_type/domain; "
        "`type` is emitted where the pin says `task_type`"
    ),
    "get_task": (
        "FIXME(#2201): sibling half of the same module -- protocol and task_type are absent "
        "and `type` is emitted where the pin says `task_type` (salesagent-prkv.89 carries the "
        "spec citation and the storyboard step)"
    ),
}


def _response_outcome_models(tool_name: str) -> list[type[BaseModel]]:
    """Every model a tool's ``_impl`` can put on the wire.

    ``_{tool}_impl`` is the naming convention the whole tools package follows, and a tool
    whose impl cannot be found this way resolves NO models -- which surfaces as a coverage
    failure rather than as silence, the property this derivation exists for.

    ``TaskResultEnvelope`` returns are unwrapped to the union inside ``response``: the
    envelope declares three fields of its own and none of them is the buyer-facing shape,
    so grading the envelope would grade nothing.
    """
    import importlib
    import pkgutil

    import src.core.tools as tools_pkg

    for module in pkgutil.walk_packages(tools_pkg.__path__, tools_pkg.__name__ + "."):
        try:
            imported = importlib.import_module(module.name)
        except Exception:  # pragma: no cover - an unimportable tool module fails elsewhere
            continue
        impl = getattr(imported, f"_{tool_name}_impl", None)
        if impl is None:
            continue
        try:
            returned = typing.get_type_hints(impl).get("return")
        except Exception:  # pragma: no cover - unresolvable annotation
            return []
        if not (isinstance(returned, type) and issubclass(returned, BaseModel)):
            return []
        if "TaskResultEnvelope" not in {base.__name__ for base in returned.__mro__}:
            return [returned]
        inner = returned.model_fields.get("response")
        if inner is None:
            return [returned]
        arms = typing.get_args(inner.annotation) or (inner.annotation,)
        return [arm for arm in arms if isinstance(arm, type) and issubclass(arm, BaseModel)]
    return []


def pinned_response_ref(model: type[BaseModel]) -> str | None:
    """The pinned response schema *model* implements, or None when it implements none.

    The response mirror of ``tests.helpers.request_schemas.pinned_request_schema_ref``,
    and deliberately the same mechanism: ``sdk_grounding`` walks the live MRO for a
    field-carrying ``adcp`` ancestor, and that ancestor's generated-module path NAMES its
    schema file. So a response model grounded in the SDK vocabulary already says which
    schema it implements, in the one place that cannot drift from it.

    It does NOT consult ``_PINNED_SCHEMA_REF``, which the request side checks first. On
    response models that attribute means something different -- ``GetMediaBuysMediaBuy``
    declares ``...get-media-buys-response.json#/properties/media_buys/items``, an ITEM
    subschema pointer used for always-include serialization -- so honouring it here would
    resolve an envelope row to an item schema.
    """
    from src.core.tools._announced_shape import sdk_grounding

    grounding = sdk_grounding(model)
    if grounding is None:
        return None
    # Private on purpose: this is the one derivation of "generated module -> schema file"
    # and the request side owns it. Re-spelling it here would be a second copy of a rule
    # that must not have two.
    from tests.helpers.request_schemas import _ref_from_generated_module

    return _ref_from_generated_module(grounding.__module__)


def _derive_response_rows() -> list[_RegistryRow]:
    """``_RegistryRow`` per REGISTERED tool whose response resolves a pinned schema.

    Membership comes from the LIVE MCP registry, the same source the request side reads,
    rather than from a hand-written list. The list it replaces had drifted in both
    directions at once: no row for three registered tools (get_adcp_capabilities,
    get_task, list_tasks) and rows for two that are not registered at all. A key set that
    can be wrong in both directions is not a membership rule.

    The success MODEL is picked, not named: of the outcome arms a tool can return, the one
    declaring every field the pinned success arm requires. Exactly one arm satisfies that
    on every registered tool -- an ambiguous or empty pick raises rather than guessing,
    because a silently-skipped tool is the failure being removed here.
    """
    rows: list[_RegistryRow] = []
    for tool_name in sorted(registered_tool_shapes()):
        models = _response_outcome_models(tool_name)
        refs = {ref for ref in (pinned_response_ref(model) for model in models) if ref is not None}
        if not refs:
            continue
        if len(refs) > 1:
            raise AssertionError(f"{tool_name}'s outcome models name different pinned schemas: {sorted(refs)}")
        ref = refs.pop()
        required = set(_success_shape(load_json_schema(ref)).get("required", []))
        candidates = [model for model in models if required <= set(model.model_fields)]
        if len(candidates) != 1:
            raise AssertionError(
                f"{tool_name}: {len(candidates)} of {[m.__name__ for m in models]} declare the pinned "
                f"success arm's required fields {sorted(required)}; expected exactly one"
            )
        override = _RESPONSE_OVERRIDES.get(tool_name, _RowOverride())
        rows.append(
            _RegistryRow(
                schema_ref=ref,
                model=candidates[0],
                sample_override=override.sample,
                declared_fields_override=override.declared_fields,
            )
        )
    return rows


def _build_alignments_from_pinned(registry: list[_RegistryRow]) -> list[ResponseAlignment]:
    """Derive an envelope-level ResponseAlignment per registered model from the
    pinned success arm — machine-complete, so a new spec-required field on any
    registered model is enforced without hand-editing this list (#1399 Plan-B)."""
    alignments: list[ResponseAlignment] = []
    for row in registry:
        arm = _success_shape(load_json_schema(row.schema_ref))
        # The REQUIRED fields (not all properties): the bug class is a spec-REQUIRED
        # field silently dropped (PR #1941 review). Demanding every OPTIONAL
        # forward-compat property be declared would over-reach — response models
        # intentionally carry optional fields via extra='allow'.
        declared = frozenset(arm.get("required", [])) - _VERSION_FIELDS
        if row.declared_fields_override is not None:
            # ADDITIVE, which is what the field has always claimed to be ("also pin
            # specific optional fields production emits"). It used to REPLACE, and the
            # one row that sets it thereby dropped every spec-required field —
            # media_buy_id, packages, confirmed_at, revision and status — out of the
            # declared-field check while reading as if it had only added two.
            declared |= row.declared_fields_override
        sample = (
            row.sample_override
            if row.sample_override is not None
            else _synthesize_sample(arm, row.schema_ref, row.model)
        )
        alignments.append(
            ResponseAlignment(
                schema_ref=row.schema_ref,
                selector=None,
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


#: Derived from the live registry, plus the two spec-grounded models whose tool is not
#: registered. Built at import because parametrize needs it there.
_RESPONSE_MODEL_REGISTRY: list[_RegistryRow] = _derive_response_rows() + _UNREGISTERED_RESPONSE_ROWS

RESPONSE_ALIGNMENTS = _build_alignments_from_pinned(_RESPONSE_MODEL_REGISTRY) + _SUPPLEMENTAL_ALIGNMENTS


def _resolve_response_item_schema(alignment: ResponseAlignment) -> dict[str, Any]:
    """The pinned (sub-)schema for a registry row — :func:`_success_shape` by row."""
    return _success_shape(
        load_json_schema(alignment.schema_ref),
        selector=alignment.selector,
        item_key=alignment.item_key,
    )


# The no-rule exits of generate_example_value that strict synthesis must refuse
# (plan §3.4 F9, GH #1900). Every row was measured at HEAD with sys.settrace on the
# function's own returns, so each drives the exit named in its id and no other.
#
# Columns:
#   lenient_value — what the lenient default (strict=False) must keep returning
#                   byte-for-byte, because the pre-existing request-side callers
#                   depend on it. Pinning it here is what keeps "add strict" from
#                   quietly becoming "change the generator".
#   from_cause    — True for the two ``except Exception`` swallows, whose raise must
#                   carry the exception it swallowed (``raise ... from exc``). That is
#                   what makes them honour load_json_schema's own HARD-FAILURE
#                   contract instead of trading one silence for another.
_NO_RULE_EXITS = [
    # NOTE: the "$ref resolved but was unreadable" exit used to be driven from here by
    # core/signal-id.json, because the resolver read only type/enum/properties and a
    # discriminated union therefore yielded {}. The resolver now folds allOf and picks a
    # oneOf/anyOf arm, so signal-id derives in full and has moved to _DERIVED_HALVES.
    # Its row is NOT replaced with another driver: a sweep of the whole pinned 3.1 tree
    # finds ZERO schemas that still reach that exit, and every row here is required to be
    # reachable in the pinned tree. The raise remains in the code as the refusal for a
    # shape a future pin might introduce; inventing a synthetic fixture to keep a row
    # alive would assert about a shape the spec does not contain.
    # The $ref did not resolve at all: swallowed by ``except Exception: return {}``.
    pytest.param("object", "thing", {"$ref": "core/unresolvable-thing.json"}, {}, True, id="ref-unresolvable-199"),
    # A guessed string embedded in a container. _synthesize_sample's sentinel check
    # compares the TOP-LEVEL value only, so a guess produced one level down is
    # returned silently — and a guess fed to a required enum/formatted field is
    # reported as a conformance failure against production, which is the exact
    # false-failure that bought envelope 'status' its blanket exclusion.
    pytest.param(
        "object",
        "wrapper",
        {"type": "object", "required": ["weird"], "properties": {"weird": {"description": "no type"}}},
        {"weird": _unsynthesized_guess("weird")},
        False,
        id="nested-string-guess-263",
    ),
    # Array items whose $ref did not resolve: swallowed by ``except Exception: pass``,
    # falling through to the invented [{}].
    pytest.param(
        "array",
        "things",
        {"type": "array", "items": {"$ref": "core/unresolvable-thing.json"}},
        [{}],
        True,
        id="array-items-ref-unresolvable-296",
    ),
    # Array items whose $ref resolved to an object that REQUIRES NOTHING: [{}] is the
    # element the generator invents when the pin gives it no property it must fill.
    # The driver used to be core/error.json, which required code+message all along —
    # the generator simply never recursed into an object-typed item and returned [{}]
    # for every one of them. It recurses now, so a schema that genuinely requires
    # nothing is needed to reach this exit; 94 pinned schemas qualify, and
    # core/async-response-data.json is one.
    pytest.param(
        "array",
        "datas",
        {"type": "array", "items": {"$ref": "core/async-response-data.json"}},
        [{}],
        False,
        id="array-items-ref-object-no-required",
    ),
    # Array of inline objects that declare no required and no *id* property: the
    # EMPTY half only — [obj] for a non-empty obj is derived, not guessed.
    pytest.param(
        "array",
        "rows",
        {"type": "array", "items": {"type": "object", "properties": {"foo": {"type": "string"}}}},
        [],
        False,
        id="array-of-objects-no-required-310-empty-half",
    ),
    # Array with no items spec at all — the element shape was never declared.
    pytest.param("array", "coordinates", {"type": "array"}, [], False, id="array-items-absent-314"),
    # Array whose items is a LIST (tuple validation), so items_spec.get(...) never
    # ran and the generator fell out of the branch entirely.
    pytest.param(
        "array",
        "coordinates",
        {"type": "array", "items": [{"type": "number"}]},
        [],
        False,
        id="array-items-list-valued-314",
    ),
    # Bare object with no properties to read: {} invented for an unread shape.
    pytest.param("object", "payload", {"type": "object"}, {}, False, id="bare-object-336"),
    # The terminal else. A union type array is not a branch this function has, and
    # confirmed_at's pinned shape is exactly {"type": ["string", "null"]} — the
    # #1900 field, reached today only because its row carries a sample_override.
    pytest.param(
        ["string", "null"],
        "confirmed_at",
        {"type": ["string", "null"]},
        None,
        False,
        id="terminal-none-338",
    ),
]

# The non-empty halves of the two split exits. A DERIVED minimal value for a shape
# the generator READ is correct and must survive strict; only the invented half is
# refused. Measured at HEAD: both reach the same return statements as their empty
# twins above, with obj non-empty.
_DERIVED_HALVES = [
    # core/pagination-response.json resolves and declares required has_more:boolean,
    # so the object is built from what was read, not guessed.
    pytest.param(
        "object", "pagination", {"$ref": "core/pagination-response.json"}, {"has_more": True}, id="198-if-half"
    ),
    pytest.param(
        "array",
        "rows",
        {"type": "array", "items": {"type": "object", "required": ["foo"], "properties": {"foo": {"type": "integer"}}}},
        [{"foo": 100}],
        id="310-non-empty-half",
    ),
    # core/signal-id.json — a schema that is ENTIRELY a discriminated oneOf, and the
    # shape that used to prove the resolver could not read one. It derives completely
    # now: the arm supplies data_provider_domain and id, and `source` comes back as the
    # pin's own const rather than a guessed string. Kept as a derived row rather than
    # deleted, because it is the live proof that both halves of that fix hold together
    # — pick an arm, then honour the const that says which arm it is.
    pytest.param(
        "object",
        "signal_id",
        {"$ref": "core/signal-id.json"},
        {"source": "catalog", "data_provider_domain": "example.com", "id": "test_id_123"},
        id="oneof-arm-with-const-discriminator",
    ),
]


class TestAllOfArmHarvest:
    """The two allOf harvests read the SAME arms, in the same order.

    ``_allof_required_fields`` and ``_allof_properties`` used to walk the top-level
    ``allOf`` in two independent loops. They must agree: a field pulled out of an
    arm's ``required`` without that arm's ``properties`` is reported as
    schema-required and as not-defined-by-the-schema in the same breath, which is
    the contradiction that produced 7 spurious failures once already.

    Nothing graded the shared walk, so these pin the two properties a refactor can
    silently break — arm ORDER (last arm wins on a key collision) and arm COVERAGE
    (every arm contributes, not just the first).
    """

    @staticmethod
    def _two_arm_schema() -> dict[str, Any]:
        """Two inline arms that collide on one property and differ on required."""
        return {
            "allOf": [
                {
                    "required": ["from_first"],
                    "properties": {"shared": {"type": "string"}, "only_first": {"type": "string"}},
                },
                {
                    "required": ["from_second"],
                    "properties": {"shared": {"type": "integer"}, "only_second": {"type": "string"}},
                },
            ]
        }

    def test_required_is_unioned_across_every_arm(self):
        """A first-arm-only walk would drop ``from_second``."""
        assert _allof_required_fields(self._two_arm_schema()) == {"from_first", "from_second"}

    def test_properties_come_from_every_arm(self):
        """A first-arm-only walk would drop ``only_second``."""
        props = _allof_properties(self._two_arm_schema())
        assert set(props) == {"shared", "only_first", "only_second"}

    def test_last_arm_wins_on_a_property_collision(self):
        """Pins the merge DIRECTION.

        The sequential ``|=`` this was extracted from let later arms overwrite
        earlier ones. A comprehension preserves that; a ``dict(...)`` built the other
        way round, or a first-wins guard, would silently flip which spec a colliding
        field is graded against — and every pinned response composes the shared
        envelope arm alongside its domain arm, so collisions are the normal case.
        """
        assert _allof_properties(self._two_arm_schema())["shared"] == {"type": "integer"}


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

    @pytest.mark.parametrize(("field_type", "field_name", "field_spec", "lenient_value", "from_cause"), _NO_RULE_EXITS)
    def test_strict_synthesis_refuses_every_no_rule_exit(
        self, field_type, field_name, field_spec, lenient_value, from_cause
    ):
        """Under ``strict``, a shape the generator has no rule for raises instead of inventing a value.

        This is a PROSPECTIVE guard, and deliberately so. Measured across the whole
        response registry, ``_synthesize_sample`` calls ``generate_example_value``
        exactly nine times — status x5, cache_scope x2, media_buy_id, revision — all
        at depth 1, zero recursion, and not one of them lands on an exit below. So
        these cases drive the shapes directly rather than through a registry row: the
        obligation is that the generator cannot invent, not that some row happens to
        exercise it today. Every shape here is reachable in the pinned 3.1 tree.

        The lenient default must be unchanged, byte-for-byte — ``strict`` is a new
        capability for the response side, not a rewrite of the request-side generator.
        """
        with pytest.raises(_CannotSynthesize) as excinfo:
            generate_example_value(field_type, field_name, field_spec, strict=True)

        if from_cause:
            assert excinfo.value.__cause__ is not None, (
                "an exit that swallowed an exception must raise FROM it — dropping the cause "
                "replaces one silence with another and loses why the schema could not be read"
            )

        assert generate_example_value(field_type, field_name, field_spec) == lenient_value

    @pytest.mark.parametrize(("field_type", "field_name", "field_spec", "derived_value"), _DERIVED_HALVES)
    def test_strict_synthesis_keeps_the_derived_half_of_a_split_exit(
        self, field_type, field_name, field_spec, derived_value
    ):
        """Two of the refused exits are one half of a two-way return; only that half is refused.

        ``return obj if obj else {}`` and ``return [obj] if obj else []`` invent on their
        EMPTY half and derive on their non-empty one. A minimal instance built out of the
        required names the generator actually read is a derived value, not a guess, so it
        must still come back under ``strict`` — refusing it would make the instrument
        unable to measure shapes it can, in fact, read.
        """
        assert generate_example_value(field_type, field_name, field_spec, strict=True) == derived_value

    def test_top_level_required_array_keeps_the_minimal_list_rule(self):
        """RATIFIED BOUNDARY: a top-level required array synthesizes to ``[]`` and does NOT raise.

        ``_synthesize_sample`` short-circuits every required array to ``[]`` before
        ``generate_example_value`` is reached. That is a RULE the docstring already
        declares ("Array required fields -> empty list (valid + minimal)"), not the
        absence of one: a required array with no ``minItems`` has ``[]`` as a spec-VALID
        derived instance, and element shapes are graded by separate ``item_key`` rows
        rather than by this envelope sample.

        The distinction this pins is the whole line strict draws: a DERIVED minimal
        value for a shape that was read is fine; an INVENTED value for an element shape
        the generator could not read (the array exits in ``_NO_RULE_EXITS``) is not.

        SCOPED TO THE ROWS THAT ACTUALLY SYNTHESIZE. This used to assert that no required
        array ANYWHERE in the registry carries ``minItems`` -- true of the twelve
        hand-written rows, and false the moment membership was derived from the live
        registry, because ``get_adcp_capabilities`` requires a non-empty
        ``supported_protocols`` and had no row. That is a claim about the whole pinned
        tree, which this test was never positioned to make; the condition the
        short-circuit actually needs is that no array it SYNTHESIZES carries ``minItems``.
        A row supplying ``sample_override`` never reaches the short-circuit, and its value
        is graded by ``test_required_fields_enforced`` constructing the model from it.
        """
        for row in _RESPONSE_MODEL_REGISTRY:
            if row.sample_override is not None:
                continue
            arm = _success_shape(load_json_schema(row.schema_ref))
            props = arm.get("properties", {})
            for fname in sorted(set(arm.get("required", [])) - _VERSION_FIELDS):
                if props.get(fname, {}).get("type") != "array":
                    continue
                assert "minItems" not in props[fname], (
                    f"{row.schema_ref} now requires a non-empty {fname!r} and synthesizes its own "
                    f"sample; the empty-list rule is no longer a spec-valid derived instance, so "
                    f"_synthesize_sample must stop using it (or the row needs a sample_override)"
                )
                assert _synthesize_sample(arm, row.schema_ref, row.model)[fname] == []


class TestResponseModelAlignment:
    """Local success models conform to the pinned AdCP response schemas."""

    @pytest.mark.parametrize("alignment", RESPONSE_ALIGNMENTS, ids=lambda a: a.model.__name__)
    def test_envelope_status_is_graded_for_every_registered_response(self, alignment: ResponseAlignment):
        """``status`` enters declared_fields for EVERY registry row that the pin requires it on.

        This is GH #1900's fifth acceptance bullet expressed as a MECHANISM rather than
        as an outcome. Two models satisfied that bullet by accident: ``status`` is
        composed onto the response through a top-level ``allOf``, and the resolver used
        to derive declared_fields returned the raw ``oneOf`` arm without merging root
        composition — so ``status`` never entered the derived set, and every check keyed
        off it (the sample, and the model_dump-survival check written for exactly the
        ``confirmed_at`` bug class) skipped the field silently on the two models where
        it mattered most.

        Asserting it here, once, for every row means a future resolver change that
        re-hides ``status`` fails on this test by name instead of quietly reducing what
        the other tests measure. A row whose pinned schema does NOT require status is
        skipped rather than forced — the assertion is "graded wherever required", not
        "present everywhere".
        """
        if alignment.item_key is not None:
            # Item-level rows describe an ELEMENT of an array (accounts[], media_buys[]),
            # where `status` is the domain status of that object — a different namespace
            # from the protocol envelope's task status. #1900 is about the envelope, so
            # grading item rows here would assert the wrong thing under the right name.
            pytest.skip(f"{alignment.model.__name__}: item-level row; envelope status is graded on the envelope row")
        item = _resolve_response_item_schema(alignment)
        if "status" not in set(item.get("required", [])):
            pytest.skip(f"{alignment.model.__name__}: the pinned schema does not require status on this shape")
        assert "status" in alignment.declared_fields, (
            f"{alignment.model.__name__}: the pinned schema REQUIRES status on this response, but it is "
            f"absent from declared_fields ({sorted(alignment.declared_fields)}), so no alignment check "
            f"grades it. This is what an unmerged oneOf arm produces — see _success_shape."
        )
        assert "status" in alignment.model.model_fields, (
            f"{alignment.model.__name__} does not declare status as a field; the pinned schema requires it "
            f"and inheriting it via extra='allow' would let it vanish with a parent config change"
        )

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
          CreateMediaBuySuccess.status, which IS invariant for a synchronous
          success — unlike confirmed_at/revision, which are columns the
          repository owns and therefore carry no default: a default there made
          the response a second producer of persisted state) -> omitting it must NOT
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


def _extends_adcp_library_type(model: type) -> bool:
    """Whether ``model`` directly extends a type DEFINED under ``adcp.types``.

    Extracted so the rule is gradeable in isolation. The obvious inline spelling —
    ``base in vars(adcp.types).values()`` — is not merely stale, it is
    NON-DETERMINISTIC: ``adcp.types`` re-exports lazily via PEP 562 ``__getattr__``,
    so that namespace is populated as a side effect of first attribute access and the
    answer depends on what any earlier import in the process happened to touch.
    ``__module__`` is a fixed property of the class, so this rule returns the same
    answer whenever it is asked.
    """
    return any((base.__module__ or "").startswith("adcp.types") for base in model.__bases__)


def _enumerate_grounded_response_models() -> set[type]:
    """Enumerate every local response model the registry MUST cover.

    This makes the registry's own inclusion rule executable instead of
    hand-listed: a model belongs iff it is (1) defined in ``src.core.schemas``
    (so imported ``Library*`` aliases, whose ``__module__`` is ``adcp.types.*``,
    are excluded), (2) extends an ``adcp`` library type directly — a base DEFINED
    under ``adcp.types``, which is NOT the same as one re-exported into
    ``vars(adcp.types)``: the SDK leaves some bases in submodules it never
    re-exports, and testing membership of that flat namespace silently drops the
    models extending them — and (3) carries a response role — its name
    ends in ``Response`` or ``Success`` (the oneOf success arm). Error arms end in
    ``Error`` and requests in ``Request``, so both are excluded; reusable
    sub-components (``Account``, ``Package``, ``Pagination``) lack the response
    suffix and are excluded too.

    A future library-grounded response model that nobody registers is therefore
    discovered here and fails the coverage gate, rather than slipping through a
    stale literal.
    """
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
            if _extends_adcp_library_type(obj):
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

    def test_enumeration_admits_models_whose_library_base_is_not_reexported(self):
        """Groundedness is decided by where the base is DEFINED, not by whether it is re-exported.

        ``_enumerate_grounded_response_models``'s own docstring states the rule as
        "``__bases__`` contains an ``adcp.types`` class", but it implements that as
        membership in ``vars(adcp.types)`` — the flat re-export namespace. A library
        base defined in a submodule that the SDK does not re-export therefore fails the
        identity check even though the model plainly extends a library type.

        Measured at HEAD: the identity rule enumerates 10 models, the ``__module__``
        rule 12 — the two below are the difference, and nothing is dropped. Both are
        already registered, so the gate stays green; what the fix buys is that their
        registry rows become deletion-protected. Until then ``SyncAccountsResponse``,
        the model GH #1900 is named for, could have its row deleted and this coverage
        gate would stay green — an instrument reporting success on a model it never
        enumerated.

        Worse than stale: ``adcp.types`` re-exports LAZILY via PEP 562 ``__getattr__``,
        so ``vars(adcp.types)`` is populated as a side effect of first attribute access.
        The identity rule's answer therefore depended on whether any earlier import in
        the process happened to touch that name — the same model was admitted or
        dropped depending on test order. Measured: ``SyncAccountsResponse`` is absent
        from ``vars`` in a file-scoped run and present in a full-suite run. Definition
        location is a stable property of the class, so the ``__module__`` rule is also
        what makes this gate deterministic.

        The rule is graded on a SYNTHETIC base rather than on the two real models,
        and that is the whole point. Asserting only that the enumeration admits
        ``SyncAccountsResponse``/``CreateMediaBuySuccess`` is VACUOUS in a whole-suite
        run: measured, the identity rule starts admitting both once
        ``test_delivery_metrics`` has executed and populated ``vars(adcp.types)``, and
        that file sorts earlier — so by the time this test runs under ``make quality``
        or ``tox -e unit`` (both whole-suite executions) the two rules already agree
        and a full revert of the fix reddens nothing. A base built here is guaranteed
        absent from that namespace no matter what ran before, so the two rules are
        forced apart deterministically.
        """
        unexported_base = type("ProbeLibraryBase", (BaseModel,), {})
        # Defined under adcp.types (new rule: grounded) but never re-exported into the
        # flat namespace (old rule: not grounded) — true in every import order.
        unexported_base.__module__ = "adcp.types.generated_poc.probe.probe_response"

        import adcp.types as adcp_types

        assert unexported_base not in vars(adcp_types).values(), (
            "the synthetic base must not be in the flat namespace, or it cannot separate the two rules"
        )

        probe = type("ProbeResponse", (unexported_base,), {})
        assert _extends_adcp_library_type(probe), (
            "groundedness must follow where the base is DEFINED (__module__ under adcp.types), not "
            "whether the SDK happens to re-export it into vars(adcp.types) — the latter is populated "
            "lazily by PEP 562 __getattr__, so it makes admission depend on import order"
        )

        unrelated = type("UnrelatedResponse", (BaseModel,), {})
        unrelated.__module__ = "src.core.schemas.something"
        assert not _extends_adcp_library_type(unrelated), "a non-library base must not be admitted"

        # And the rule, applied to the real tree, admits the two models whose bases the
        # identity check missed. Order-dependent on its own (see above), so it rides
        # behind the synthetic assertions rather than carrying the grade.
        grounded = _enumerate_grounded_response_models()
        unadmitted = {SyncAccountsResponse, CreateMediaBuySuccess} - grounded
        assert not unadmitted, (
            f"library-grounded response models the enumeration failed to admit: "
            f"{sorted(m.__name__ for m in unadmitted)} — their registry rows are unprotected, so "
            f"deleting one leaves the coverage gate green"
        )


def _pinned_constraint(ref: str, node_path: tuple[str | int, ...], field: str, keyword: str) -> Any:
    """Read one JSON-Schema keyword off a field in the PINNED schema tree.

    ``node_path`` walks to the object that declares ``properties`` — the pins
    below put the field under ``oneOf/0`` (a response union arm) or under
    ``$defs/signal`` — so the caller names the node instead of a search guessing
    which of several same-named fields it found.

    The keyword must be PRESENT: a pin that silently stopped declaring the bound
    would otherwise make the caller assert against ``None`` and pass.
    """
    node: Any = pinned_schema.load(ref)
    for step in node_path:
        node = node[step]
    spec = node["properties"][field]
    assert keyword in spec, f"{ref} {'/'.join(map(str, node_path))}.properties.{field} declares no {keyword!r}: {spec}"
    return spec[keyword]


class TestPinnedBoundsUnreachableFromAnyRequest:
    """Bounds the pin declares that NO request payload can drive production across.

    Seven local fields redeclared an adcp parent
    field and drop the bound the pin carries. Four are reachable from a request
    and are graded behaviourally, cross-transport, in
    tests/bdd/features/local-constraint-relaxation-rejections.feature. These three
    are not reachable, for reasons measured per field and recorded in each test —
    so they are graded here, at the model, which is the only place the value can
    be presented at all. A behavioural row for any of them would have to fake the
    payload it claims a buyer could send.

    Each test reads the bound from the pinned schema rather than restating it, so
    a spec change moves the test instead of silently invalidating it.
    """

    def test_create_media_buy_success_refuses_a_revision_below_the_pinned_minimum(self):
        """revision=0 must not be constructible on the create success envelope.

        Not behaviourally reachable: ``media_buys.revision`` is NOT NULL DEFAULT 1
        (src/core/database/models.py:1116), so no persisted row can carry 0 and no
        request can steer production into emitting one. The bound protects the
        buyer's optimistic-concurrency token against a SELLER-side defect — a
        response fabricated or migrated with a zero revision — which is why the
        model is the grading locus.
        """
        minimum = _pinned_constraint("media-buy/create-media-buy-response.json", ("oneOf", 0), "revision", "minimum")

        with pytest.raises(ValidationError):
            CreateMediaBuySuccess(
                media_buy_id="mb_bounds_probe",
                confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
                revision=minimum - 1,
                packages=[],
            )

    def test_update_media_buy_success_refuses_a_revision_below_the_pinned_minimum(self):
        """revision=0 must not be constructible on the update success envelope.

        Same unreachability as the create sibling, and graded separately rather
        than parametrized with it: they are two independently-declared local
        fields, and one grader standing in for both is the substitution this epic
        exists to remove. The update envelope's revision is the value the buyer
        feeds back into the NEXT conditional update, so a zero here is the one
        that would strand a buyer mid-sequence.
        """
        minimum = _pinned_constraint("media-buy/update-media-buy-response.json", ("oneOf", 0), "revision", "minimum")

        with pytest.raises(ValidationError):
            UpdateMediaBuySuccess(media_buy_id="mb_bounds_probe", revision=minimum - 1)

    def test_signal_refuses_an_empty_deployments_list(self):
        """A Signal must carry at least one deployment.

        No behavioural row is authorable, and faking one would be the dishonest
        move: ``_get_signals_impl`` is an explicit mock whose only producers are
        six hardcoded ``Signal(...)`` literals at src/core/tools/signals.py:90-155,
        each passing exactly one ``SignalDeployment`` (lines 98/109/120/131/142/153).
        No request parameter reaches the deployments list, so no scenario can
        present an empty one — the model is the whole surface.

        The pin is ``core/wholesale-feed-event.json#/$defs/signal``, which is what
        ``src.core.schemas.Signal`` extends. Deliberately NOT
        ``signals/get-signals-response.json``: that sibling types the SAME
        deployments array with no minItems at all, so a reader who checks only the
        tool's own response schema would conclude this bound is unfounded. The
        bound belongs to the entity, and the entity's pin declares it.
        """
        min_items = _pinned_constraint("core/wholesale-feed-event.json", ("$defs", "signal"), "deployments", "minItems")
        assert min_items == 1, f"pin changed: $defs.signal.deployments.minItems is {min_items}, not 1"

        with pytest.raises(ValidationError):
            Signal(
                name="bounds probe",
                description="a signal presented with no deployment",
                signal_agent_segment_id="seg_bounds_probe",
                signal_type="marketplace",
                deployments=[],
            )

    def test_package_request_creatives_bounds_match_the_pin(self):
        """``PackageRequest.creatives`` carries the pin's minItems AND maxItems.

        This one needs its own grader, and the reason is structural rather than
        incidental. The other four hand-restated bounds are protected by the
        inheritance guard's metadata-superset arm: if the pin moves, the parent's
        metadata stops being a subset of the local field's and the guard reddens.

        That arm is only reached for fields the guard finds ADMISSIBLE. This field
        fails the SHAPE clause — ``issubclass(schemas.creative.Creative,
        adcp...CreativeAsset)`` is False, because the local element type is a
        substitution rather than a narrowing — so it keeps its KNOWN_OVERRIDES row,
        and **a row absorbs any later metadata divergence silently**. The drift
        protection the rest of the change-set relies on is dead here.

        ``max_length=100`` in particular was graded by nothing at all: every
        behavioural row exercises the lower bound.
        """
        # Read from package-request.json directly, not through
        # create-media-buy-request.json: that schema's packages.items is a bare
        # {"$ref": "package-request.json"}, so the bounds are not there to read. The
        # entity's own schema is both the reachable location and the correct citation
        # — the same package type is referenced by update-media-buy-request.json's
        # packages AND new_packages, and all three carry these bounds because they all
        # point here.
        min_items = _pinned_constraint("media-buy/package-request.json", (), "creatives", "minItems")
        max_items = _pinned_constraint("media-buy/package-request.json", (), "creatives", "maxItems")

        assert (min_items, max_items) == (1, 100), (
            f"pin changed: packages.items.creatives bounds are ({min_items}, {max_items}), not (1, 100)"
        )

        from src.core.schemas import PackageRequest

        declared = {type(m).__name__: m for m in PackageRequest.model_fields["creatives"].metadata}
        assert getattr(declared.get("MinLen"), "min_length", None) == min_items, (
            f"local min_length does not match the pin's minItems={min_items}: {declared}"
        )
        assert getattr(declared.get("MaxLen"), "max_length", None) == max_items, (
            f"local max_length does not match the pin's maxItems={max_items}: {declared}"
        )


#: The tool -> DTO reading moved to tests/helpers/registered_tools.py, and the tool ->
#: schema binding to tests/helpers/request_schemas.py, so the DTO grading here and the
#: payload grading in the request-FACTORY suite read the same derivation rather than two
#: tables that can drift onto different schemas.


class TestNoNonSpecFieldsAreAdvertised:
    """A request DTO must not carry a buyer-visible field the pinned schema does not define.

    This is the EXTRA direction. The suite already checked that our models ACCEPT every spec
    field (test_model_accepts_all_schema_fields) and REQUIRE what the spec requires
    (test_model_has_all_required_fields). Nothing checked the other way, so a field invented
    locally was published to buyers as though the spec defined it -- the announced shape
    derives from OUR model, not the library's.

    The instance this caught: ListAccountsRequest declared `idempotency_key`, commented as
    read-tool-idempotency tolerance. account/list-accounts-request.json declares no such
    property and declares `additionalProperties: true` -- the duty is tolerance, which the
    boundary already discharges, so declaring it advertised a field 3.1.1 does not define on
    MCP and REST. Both the field and the wrapper parameter have been removed; a field removed
    from the model while the wrapper still declares the parameter stays advertised.

    What runs at RUNTIME is stronger than this class and lives in
    ``src.core.tools._announced_shape``: registration REFUSES a tool whose DTO announces a
    field no adcp library type declares, so that state is unreachable rather than reported.
    This class is the half the refusal cannot do, and the reason it is not redundant: the
    refusal's authority is the SDK, and the SDK is a cross-check on the pinned schemas, not
    the authority (CLAUDE.md). A field the SDK itself declares and the spec does not sails
    straight past the refusal and is caught only here.

    Two kinds of field are exempt, both by DECLARATION on the model rather than by a row in
    this file:

    * ``exclude=True`` -- internal, never announced on any transport, never serialized.
    * ``_NON_SCHEMA_FIELDS`` -- carried on purpose, with the reason. Read off the model so
      there is ONE declaration, consumed by both the runtime refusal and these tests.
    """

    @pytest.mark.parametrize("tool_name", sorted(graded_request_schemas()))
    def test_the_advertised_shape_carries_no_field_the_schema_lacks(self, tool_name: str) -> None:
        """What buyers actually SEE, graded against the spec.

        Keyed on the advertised parameter set rather than on model_fields, because that is
        the thing the ticket is about: a field only misleads a buyer once it is published.
        """
        from src.core.tools._announced_shape import non_schema_fields

        schema_ref, model_class = graded_request_schemas()[tool_name]
        _, advertised = registered_tool_shapes()[tool_name]
        spec_fields = set(load_json_schema(schema_ref).get("properties", {}))
        assert spec_fields, f"{schema_ref} declares no properties — the pin moved, fix the ref"

        extra = sorted(advertised - spec_fields - _VERSION_FIELDS - set(non_schema_fields(model_class)))

        assert not extra, (
            f"{tool_name} advertises {extra}, which {schema_ref} does not define. Buyers read "
            f"the advertised shape as the contract, so this publishes a field as if it were "
            f"spec. Remove it, mark it exclude=True if it is genuinely internal, or add it to "
            f"{model_class.__name__}._NON_SCHEMA_FIELDS with the reason it is carried anyway."
        )

    @pytest.mark.parametrize("tool_name", sorted(graded_request_schemas()))
    def test_no_locally_declared_field_is_absent_from_the_schema(self, tool_name: str) -> None:
        """The LATENT case: a field our subclass adds that no wrapper has exposed yet.

        The test above only sees published fields, and the runtime refusal only fires on
        published ones too -- so a locally-invented field sits harmlessly in the DTO until
        somebody adds the matching wrapper parameter, at which point it is published. Graded
        here so the departure is declared BEFORE that, not discovered by a buyer after.

        Scoped to fields OUR subclass declares (nothing in the adcp ancestry declares them),
        which is what makes this different from the test above: a field the SDK ships that
        the pinned schema lacks is SDK-vs-spec drift, not something this repo can fix by
        deleting a line, and it is caught above the moment it reaches a buyer.
        """
        from src.core.tools._announced_shape import library_declared_fields, non_schema_fields

        schema_ref, model_class = graded_request_schemas()[tool_name]
        spec_fields = set(load_json_schema(schema_ref).get("properties", {}))

        locally_declared = {
            name
            for name, field in model_class.model_fields.items()
            if not field.exclude and name not in library_declared_fields(model_class)
        }
        extra = sorted(locally_declared - spec_fields - _VERSION_FIELDS - set(non_schema_fields(model_class)))

        assert not extra, (
            f"{model_class.__name__} ({tool_name}) declares {extra}, which {schema_ref} does "
            f"not define and no adcp library type declares either. Remove it, mark it "
            f"exclude=True if it is internal, or add it to "
            f"{model_class.__name__}._NON_SCHEMA_FIELDS with the reason it is carried anyway."
        )

    def test_every_registered_tool_is_graded_or_provably_has_no_spec_schema(self) -> None:
        """No tool may drop out of the grading by resolving no schema.

        The escape this closes is the cheap one: a tool's DTO stops resolving a pinned
        schema -- a new tool lands with no SDK grounding, or somebody deletes a
        ``_PINNED_SCHEMA_REF`` line -- and from then on nothing compares it to anything,
        greenly. Membership is read from the live registry, and the only way to sit
        outside the grading is for the PINNED TREE to hold no request schema for the
        tool, which is verified here rather than taken on trust.

        The verification searches by NAME COVERAGE, not by exact filename. The version
        this replaces probed ``<tool-name>-request.json`` and nothing else, so
        ``get_task`` -- whose schema is ``get-task-status-request.json`` -- would have
        passed as "no schema exists" the moment its binding was dropped. Every schema
        whose stem's words cover the tool's is reported, so the extra-word case fails
        loudly instead.
        """
        ungraded = sorted(set(registered_tool_shapes()) - set(graded_request_schemas()))

        resolvable = {tool: cands for tool in ungraded if (cands := pinned_request_schema_candidates(tool))}
        assert not resolvable, (
            f"{ {t: sorted(c) for t, c in resolvable.items()} } resolve no pinned request "
            f"schema, but the pinned tree holds one whose name covers each. Their DTOs are "
            f"graded against nothing. Ground the DTO in the adcp type for that schema, or "
            f"declare _PINNED_SCHEMA_REF on it naming the schema it implements."
        )


def pinned_response_schema_candidates(tool_name: str) -> dict[str, str]:
    """``ref -> reason`` for every pinned RESPONSE schema that plausibly belongs to *tool_name*.

    The negative proof behind "this tool genuinely has no pinned response schema", and the
    same token-subset rule its request-side sibling
    (``tests.helpers.request_schemas.pinned_request_schema_candidates``) uses and for the
    same reason: an exact-filename probe reports ``get_task`` -> no schema, because the
    file is ``get-task-status-response.json``, and reporting that as "nothing to grade" is
    precisely how a tool goes silently ungraded.

    DRY DEBT, stated rather than hidden: this differs from the request-side helper only in
    the glob and the wording, so the two should be ONE function taking the suffix. It is
    written here because ``tests/helpers/`` belongs to another lane in the change this
    landed in; fold them together when that lane is free.
    """
    wanted = set(tool_name.split("_"))
    root = pinned_schema.schema_root()
    return {
        f"{path.parent.name}/{path.name}": f"stem {path.stem!r} covers {sorted(wanted)}"
        for path in sorted(root.rglob("*-response.json"))
        if "bundled" not in path.relative_to(root).parts and wanted <= set(path.stem.split("-"))
    }


class TestEveryRegisteredToolsResponseIsGraded:
    """Membership on the RESPONSE side, keyed by TOOL rather than by model.

    The sibling gate ``TestResponseAlignmentCoverage`` enumerates MODELS, so a tool that
    returns a raw dict is invisible to it -- there is no model to enumerate. That is not a
    weaker version of this gate, it is a different question, and neither subsumes the
    other: one asks "is every grounded model graded", this asks "is every registered
    tool's response graded". ``list_tasks`` and ``get_task`` build dicts in
    ``src/core/tools/task_management.py`` and passed the model gate by being absent from
    its universe.

    WHAT THIS AXIS CANNOT SEE. It grades DECLARATION -- can production carry the field at
    all -- not EMISSION, whether the field survives onto the wire. A model that declares a
    pinned-required field and a serializer that drops it passes everything here. That is a
    live bug class (prebid/salesagent#1928, #2012 are both filed as it) and it needs a wire
    dispatch per tool, which this suite's method cannot supply: everything here is static
    and offline by construction. Do not "extend" this class to cover it.
    """

    def test_every_registered_tool_is_graded_or_provably_has_no_response_schema(self):
        """A registered tool is derived, a named known gap, or has no pinned response schema."""
        derived = {row.schema_ref for row in _derive_response_rows()}
        ungraded = []
        for tool_name in sorted(registered_tool_shapes()):
            refs = {ref for ref in (pinned_response_ref(m) for m in _response_outcome_models(tool_name)) if ref}
            if refs & derived:
                continue
            if tool_name in _UNGRADED_RESPONSES:
                continue
            if candidates := pinned_response_schema_candidates(tool_name):
                ungraded.append((tool_name, sorted(candidates)))
        assert not ungraded, (
            f"{ungraded} resolve no graded pinned response schema, but the pinned tree holds one "
            f"whose name covers each -- so what they put on the wire is graded by nothing. Ground "
            f"the tool's response in the adcp type for that schema, or add it to "
            f"_UNGRADED_RESPONSES with the issue that tracks the gap."
        )

    def test_known_response_gaps_are_still_real(self):
        """Every ``_UNGRADED_RESPONSES`` row must still describe a live gap.

        THE HALF THAT MAKES A KNOWN-GAP SET DIFFERENT FROM AN EXCUSE. A row asserts two
        things -- the pinned tree defines a response schema for this tool, and production
        has no spec-grounded model that could be graded against it -- and both are
        re-measured here on every run. Give ``list_tasks`` a real response model and this
        fails by name, so the row cannot outlive its defect.

        That failure mode is not hypothetical. A ``deliver_mcp`` allowlist row for exactly
        this ``list_tasks`` gap was deleted under the note "that gap is now fixed in
        production"; it was not fixed, nothing re-measured it, and the deletion was
        recorded as a ratchet shrink.
        """
        for tool_name, reason in sorted(_UNGRADED_RESPONSES.items()):
            assert "#" in reason, f"{tool_name}'s known-gap row names no issue: {reason!r}"
            assert pinned_response_schema_candidates(tool_name), (
                f"{tool_name} is listed as an ungraded response, but the pinned tree defines no "
                f"response schema whose name covers it -- there is no gap here to track. Delete the row."
            )
            grounded = [m.__name__ for m in _response_outcome_models(tool_name) if pinned_response_ref(m)]
            assert not grounded, (
                f"{tool_name} now returns spec-grounded {grounded}, so the derivation grades it and "
                f"its _UNGRADED_RESPONSES row is stale. Delete the row ({reason})."
            )

    def test_the_gap_set_is_not_a_way_to_opt_out(self):
        """Anti-vacuity: only tools the derivation genuinely cannot reach may be listed.

        Without this, the coverage gate above is satisfiable by adding any inconvenient
        tool to ``_UNGRADED_RESPONSES``. A tool the derivation DOES reach is graded, so
        listing it is either a mistake or an opt-out; both are failures.
        """
        derived_tools = {
            tool_name
            for tool_name in registered_tool_shapes()
            if any(pinned_response_ref(m) for m in _response_outcome_models(tool_name))
        }
        overlap = sorted(derived_tools & set(_UNGRADED_RESPONSES))
        assert not overlap, f"{overlap} are graded by the derivation and must not be in _UNGRADED_RESPONSES"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
