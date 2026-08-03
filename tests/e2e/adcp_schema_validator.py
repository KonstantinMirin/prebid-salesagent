"""AdCP JSON Schema Validator for E2E Tests — pinned to the installed SDK's schemas.

Validates requests and responses against the AdCP schemas BUNDLED with the
pinned ``adcp`` SDK (adcp==6.6.0 → AdCP spec 3.1.1) — never against the live
adcontextprotocol.org registry. The live registry serves "latest", which
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

import functools
import hashlib
import json
from pathlib import Path
from typing import Any

import referencing
from jsonschema.validators import Draft7Validator
from referencing.jsonschema import DRAFT7


class SchemaError(Exception):
    """Base exception for schema validation errors."""


class SchemaValidationError(SchemaError):
    """Raised when JSON validation fails."""

    def __init__(self, message: str, validation_errors: list[str], json_path: str = ""):
        super().__init__(message)
        self.validation_errors = validation_errors
        self.json_path = json_path


def _sdk_schema_root() -> Path:
    """Locate the pinned spec version's schema tree inside the installed SDK.

    The SDK stores schemas under ``adcp/_schemas/<major.minor>/`` (e.g. the
    3.1.1 spec lives in ``_schemas/3.1/``; its ``index.json`` carries the full
    ``adcp_version``).
    """
    import adcp

    spec_version = adcp.get_adcp_spec_version()
    major_minor = ".".join(spec_version.split(".")[:2])
    root = Path(adcp.__file__).parent / "_schemas" / major_minor
    if not root.is_dir():
        raise SchemaError(
            f"Installed adcp SDK (spec {spec_version}) has no bundled schema tree at {root} — "
            "the SDK layout changed; update _sdk_schema_root()."
        )
    return root


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
        """Resolve a version-root-relative ref to a file, preferring bundled."""
        bundled = self.schema_root / "bundled" / relative_ref
        if bundled.is_file():
            return bundled
        plain = self.schema_root / relative_ref
        if plain.is_file():
            return plain
        raise SchemaError(
            f"Schema {relative_ref!r} not found in the pinned SDK tree {self.schema_root} "
            "(checked bundled/ and the plain tree)"
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

                Bundled schemas are self-contained, so this only fires for a
                schema loaded from the plain tree. A miss raises (surfacing as
                a validation error naming the ref) instead of substituting a
                reject-everything schema.
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
        """Find the schema reference for a specific task and type."""
        index = await self.get_schema_index()

        # Look in media-buy tasks first
        media_buy_tasks = index.get("schemas", {}).get("media-buy", {}).get("tasks", {})
        if task_name in media_buy_tasks:
            task_info = media_buy_tasks[task_name]
            if request_or_response in task_info:
                return task_info[request_or_response]["$ref"]

        # Look in signals tasks
        signals_tasks = index.get("schemas", {}).get("signals", {}).get("tasks", {})
        if task_name in signals_tasks:
            task_info = signals_tasks[task_name]
            if request_or_response in task_info:
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
            # Don't fail if schema not found - log warning instead
            print(f"Warning: No request schema found for task '{task_name}'")
            return

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
            # Don't fail if schema not found - log warning instead
            print(f"Warning: No response schema found for task '{task_name}'")
            return

        # Extract AdCP payload from protocol wrapper if present
        adcp_payload = self._extract_adcp_payload(response_data)

        await self._validate_against_schema(schema_ref, adcp_payload, f"{task_name} response")

    def _extract_adcp_payload(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the AdCP payload from protocol wrapper fields.

        MCP and A2A protocols may add wrapper fields like:
        - message: Human-readable message from the transport layer
        - context_id: Session continuity identifier
        - errors: Transport-layer errors (not part of AdCP spec)
        - clarification_needed: Non-spec field that should be removed

        This method removes these protocol-layer fields and returns only
        the AdCP payload for validation.

        Args:
            response_data: The full response including protocol wrapper fields

        Returns:
            The AdCP payload with protocol-layer fields removed
        """
        # List of known protocol-layer fields that are not part of AdCP spec
        protocol_fields = {
            "message",  # MCP/A2A transport layer message
            "context_id",  # MCP session continuity
            "clarification_needed",  # Non-spec field
            "errors",  # Transport-layer errors (not in AdCP spec)
            # Note: Some AdCP responses do have "error" fields defined in spec,
            # but "errors" (plural) is typically a transport-layer addition
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
                    if hasattr(error, "schema_path") and error.schema_path:
                        schema_path = ".".join(str(p) for p in error.schema_path)
                        error_msg += f" (schema path: {schema_path})"

                    error_messages.append(error_msg)

                raise SchemaValidationError(
                    f"Schema validation failed for {context}", error_messages, json_path=path if errors else ""
                )

        except SchemaValidationError:
            # Re-raise schema validation errors without wrapping them
            raise
        except Exception as e:
            raise SchemaValidationError(f"Unexpected error validating {context}: {e}", [str(e)])


# Decorator functions for easy integration with tests


def validate_adcp_request(task_name: str):
    """
    Decorator to validate AdCP request data.

    Usage:
        @validate_adcp_request("get-products")
        async def test_method(self):
            # Test implementation
            pass
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request data from kwargs or test method
            # This would need to be integrated with the specific test patterns
            result = await func(*args, **kwargs)
            return result

        return wrapper

    return decorator


def validate_adcp_response(task_name: str):
    """
    Decorator to validate AdCP response data.

    Usage:
        @validate_adcp_response("get-products")
        async def test_method(self):
            # Test returns response data
            return response_data
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Validate the result if it looks like response data
            if isinstance(result, dict):
                async with AdCPSchemaValidator() as validator:
                    await validator.validate_response(task_name, result)

            return result

        return wrapper

    return decorator
