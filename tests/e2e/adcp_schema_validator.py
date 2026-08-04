"""AdCP JSON Schema Validator for E2E Tests — pinned to the installed SDK's schemas.

Validates requests and responses against the AdCP schemas BUNDLED with the
pinned ``adcp`` SDK (see docs/adcp-spec-version.md for the current pin and
bump procedure) — never against the live adcontextprotocol.org registry. The
live registry serves "latest", which
drifts ahead of the repo's pin: on 2026-08-01 upstream PR #6133 canonicalized
the live schemas' $ref URIs and broke remote ref resolution here overnight
with zero contract change, and before that #1308 tracked payload-vs-latest
drift. Validating against the pin makes CI deterministic and grades the same
contract production is built against. The SDK↔spec mapping is enforced by
tests/unit/test_adcp_spec_version.py.

The SDK ships each spec version's schemas twice: a plain tree with $refs and
a ``bundled/`` tree with every $ref inlined (fully self-contained). Schemas
are loaded from ``bundled/`` first, so the old failure mode — an unresolvable
$ref silently degrading to a reject-everything fallback schema — cannot
occur; an unresolvable reference now raises loudly instead.

Usage:
    async with AdCPSchemaValidator() as validator:
        await validator.validate_response("get-products", response_data)
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import referencing
from jsonschema.validators import Draft7Validator
from referencing.jsonschema import DRAFT7

from tests.helpers.sdk_schema_root import sdk_schema_root as _sdk_schema_root


class SchemaError(Exception):
    """Base exception for schema validation errors."""


class SchemaValidationError(SchemaError):
    """Raised when JSON validation fails."""

    def __init__(self, message: str, validation_errors: list[str], json_path: str = ""):
        super().__init__(message)
        self.validation_errors = validation_errors
        self.json_path = json_path


class AdCPSchemaValidator:
    """Validator for AdCP protocol JSON schemas, pinned to the installed SDK.

    All schemas load from the SDK package on disk; no network access.
    """

    def __init__(self) -> None:
        self.schema_root = _sdk_schema_root()

        # Schema registry and compiled validators cache
        self._schema_registry: dict[str, dict[str, Any]] = {}
        self._compiled_validators: dict[str, Draft7Validator] = {}
        self._index_cache: dict[str, Any] | None = None

    async def __aenter__(self):
        """Async context manager entry (kept async for call-site compatibility)."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with open(path) as f:
            return json.load(f)

    def _normalize_ref(self, schema_ref: str) -> str:
        """Map any historical $ref form to a path relative to the version root.

        Accepts absolute URLs (``https://adcontextprotocol.org/schemas/latest/…``),
        site-rooted paths (``/schemas/v1/…``, ``/schemas/3.1.1/…``), and paths
        already relative to the version root (``media-buy/get-products-request.json``,
        the form the SDK index uses). The version segment is discarded — the
        installed SDK's tree IS the pinned version.
        """
        ref = schema_ref
        if ref.startswith(("http://", "https://")):
            host_and_path = ref.split("://", 1)[1]
            ref = "/" + host_and_path.split("/", 1)[1] if "/" in host_and_path else ""
        if ref.startswith("/schemas/"):
            parts = ref.split("/", 3)  # ['', 'schemas', '<version>', '<relative path>']
            ref = parts[3] if len(parts) == 4 else ""
        if not ref or ref.startswith(("/", "..")):
            raise SchemaError(f"Cannot resolve schema reference {schema_ref!r} against the pinned SDK schema tree")
        return ref

    def _schema_path(self, relative_ref: str) -> Path:
        """Resolve a version-root-relative ref inside the self-contained bundled tree.

        Only ``bundled/`` is served: the plain tree's schemas carry relative
        ``../core/x.json`` / bare-sibling ``$ref``s that cannot be resolved
        without threading a base directory through ``_normalize_ref``, so a
        plain-tree fallback would trade this loud error for the resolver's own.
        """
        bundled_root = (self.schema_root / "bundled").resolve()
        candidate = (bundled_root / relative_ref).resolve()
        # Containment check: closes traversal forms a prefix check misses
        # (e.g. 'media-buy/../../../../etc/hosts') before any filesystem probe.
        if not candidate.is_relative_to(bundled_root):
            raise SchemaError(f"Schema reference {relative_ref!r} escapes the pinned SDK schema tree")
        if candidate.is_file():
            return candidate
        raise SchemaError(
            f"Schema {relative_ref!r} not found under {bundled_root} — the validator serves only "
            "the SDK's self-contained bundled tree"
        )

    async def get_schema_index(self) -> dict[str, Any]:
        """Get the pinned schema index."""
        if self._index_cache is None:
            self._index_cache = self._load_json(self.schema_root / "index.json")
        return self._index_cache

    async def get_schema(self, schema_ref: str) -> dict[str, Any]:
        """Get a schema by reference, using cache when possible."""
        if schema_ref not in self._schema_registry:
            self._schema_registry[schema_ref] = self._load_json(self._schema_path(self._normalize_ref(schema_ref)))
        return self._schema_registry[schema_ref]

    def _get_compiled_validator(self, schema: dict[str, Any]) -> Draft7Validator:
        """Get a compiled validator for a schema, with caching."""
        # Create a hash of the schema for caching
        schema_hash = hashlib.md5(json.dumps(schema, sort_keys=True).encode()).hexdigest()

        if schema_hash not in self._compiled_validators:

            def _retrieve(uri: str) -> referencing.Resource:
                """Resolve a $ref against the pinned SDK tree — loudly, never a fallback.

                Bundled schemas are self-contained, so this should never fire;
                if it does, the miss raises (naming the ref) instead of
                substituting a reject-everything schema.
                """
                return DRAFT7.create_resource(self._load_json(self._schema_path(self._normalize_ref(uri))))

            registry = referencing.Registry(retrieve=_retrieve)
            # Seed the registry with the root schema
            root_resource = DRAFT7.create_resource(schema)
            root_id = schema.get("$id", "")
            if root_id:
                registry = registry.with_resource(root_id, root_resource)

            self._compiled_validators[schema_hash] = Draft7Validator(schema, registry=registry)

        return self._compiled_validators[schema_hash]

    async def _find_schema_ref_for_task(self, task_name: str, request_or_response: str) -> str | None:
        """Find the schema reference for a specific task and type.

        Searches every section of the pinned index, in the index's own key
        order (NOT sorted — at least one task name, 'list-creative-formats',
        is defined differently in two sections: media-buy's sales-agent-facing
        format_ids+creative_agents list vs. creative's authoritative full
        format definitions. Index order puts media-buy first, so that's the
        match returned; re-sorting the sections would silently flip it.
        """
        index = await self.get_schema_index()

        for section in index.get("schemas", {}).values():
            task_info = section.get("tasks", {}).get(task_name)
            if task_info and request_or_response in task_info:
                return task_info[request_or_response]["$ref"]

        return None

    async def validate_request(self, task_name: str, request_data: dict[str, Any]) -> None:
        """
        Validate a request against the pinned AdCP schema.

        Args:
            task_name: Name of the AdCP task (e.g., "get-products")
            request_data: The request data to validate

        Raises:
            SchemaValidationError: If validation fails
        """
        schema_ref = await self._find_schema_ref_for_task(task_name, "request")
        if not schema_ref:
            raise SchemaError(f"No request schema found for task {task_name!r} in the pinned index")

        await self._validate_against_schema(schema_ref, request_data, f"{task_name} request")

    async def validate_response(self, task_name: str, response_data: dict[str, Any]) -> None:
        """
        Validate a response against the pinned AdCP schema.

        This method understands protocol layering - it will extract the AdCP payload
        from MCP/A2A wrapper fields and validate only the payload against the schema.

        Args:
            task_name: Name of the AdCP task (e.g., "get-products")
            response_data: The response data to validate (may include protocol wrapper fields)

        Raises:
            SchemaValidationError: If validation fails
        """
        schema_ref = await self._find_schema_ref_for_task(task_name, "response")
        if not schema_ref:
            raise SchemaError(f"No response schema found for task {task_name!r} in the pinned index")

        # Extract AdCP payload from protocol wrapper if present
        adcp_payload = self._extract_adcp_payload(response_data)

        await self._validate_against_schema(schema_ref, adcp_payload, f"{task_name} response")

    def _extract_adcp_payload(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the AdCP payload from protocol wrapper fields.

        The pinned schema's response envelope is an allOf of the version
        fields plus a "Protocol Envelope" arm (e.g.
        get-products-response.json allOf[1]) that spec-defines message and
        context_id — both are populated by the protocol layer, not the
        Pydantic response model, but they ARE modeled and typed on the wire
        envelope the buyer actually receives, so they must be graded, not
        exempted. "errors" is a spec-defined top-level property on several
        response schemas too (and required on some "failed"/partial-failure
        oneOf arms) — stripping it previously let a payload that should fail
        validation (e.g. status="failed" with no errors array) pass
        silently. Only "clarification_needed" has no basis in the pinned
        schemas and stays stripped.

        Args:
            response_data: The full response including protocol wrapper fields

        Returns:
            The AdCP payload with genuinely non-spec fields removed
        """
        # The only strip-set entry with no basis in the pinned schemas.
        protocol_fields = {
            "clarification_needed",
        }

        # Create a copy of the response without protocol fields
        adcp_payload = {}
        for key, value in response_data.items():
            if key not in protocol_fields:
                adcp_payload[key] = value

        return adcp_payload

    async def _validate_against_schema(self, schema_ref: str, data: dict[str, Any], context: str = "") -> None:
        """
        Validate data against a specific schema reference.

        Args:
            schema_ref: Reference to the schema to validate against
            data: Data to validate
            context: Context string for error messages

        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            schema = await self.get_schema(schema_ref)
            validator = self._get_compiled_validator(schema)

            errors = list(validator.iter_errors(data))
            if errors:
                error_messages = []
                for error in errors:
                    # Build JSON path
                    path = ".".join(str(p) for p in error.absolute_path)
                    if not path:
                        path = "root"

                    # Include more detailed error information
                    error_msg = f"At {path}: {error.message}"
                    if error.schema_path:
                        schema_path = ".".join(str(p) for p in error.schema_path)
                        error_msg += f" (schema path: {schema_path})"

                    error_messages.append(error_msg)

                raise SchemaValidationError(
                    f"Schema validation failed for {context}", error_messages, json_path=path if errors else ""
                )

        except SchemaValidationError:
            # Re-raise schema validation errors without wrapping them
            raise
        except SchemaError:
            # Schema-RESOLUTION failures (bad ref, missing file) must not be
            # wrapped as SchemaValidationError: callers branch on that type to
            # mean "the payload violates the contract". Subclass arm above,
            # base-class arm here — order matters.
            raise
        except Exception as e:
            raise SchemaValidationError(f"Unexpected error validating {context}: {e}", [str(e)])
