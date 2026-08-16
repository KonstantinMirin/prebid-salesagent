"""Guard: Schema classes must extend adcp library base types.

Every schema class in src/core/schemas.py that corresponds to an adcp library
type must inherit from it via the Library* alias pattern. This prevents field
drift, ensures forward compatibility with adcp upgrades, and maintains protocol
compliance.

Scanning approach: Introspection — import the schemas module, discover all
Library* aliases (imported from adcp), then verify that for each Library alias,
the corresponding local class inherits from it.

beads: salesagent-v0kb (structural-guard epic)
"""

import importlib
import inspect

import pytest

from tests.unit._architecture_helpers import assert_violations_match_allowlist


def _get_schemas_source_files() -> list["Path"]:
    """Get all Python source files in the schemas package.

    Handles both the old single-file layout (src/core/schemas.py) and
    the new package layout (src/core/schemas/__init__.py + submodules).
    """
    from pathlib import Path

    schemas_path = Path("src/core/schemas")
    if schemas_path.is_dir():
        return sorted(schemas_path.glob("**/*.py"))
    single_file = Path("src/core/schemas.py")
    if single_file.exists():
        return [single_file]
    raise FileNotFoundError("Cannot find src/core/schemas.py or src/core/schemas/ package")


def _get_library_type_mapping() -> dict[str, type]:
    """Build mapping of local class names to their expected library base types.

    Scans src.core.schemas for all imports aliased as Library*. For each such
    import, the local class with the un-prefixed name should inherit from it.

    Returns dict like: {"Product": <class adcp.types.Product>, ...}
    """
    import ast

    mapping: dict[str, type] = {}

    for schemas_path in _get_schemas_source_files():
        source = schemas_path.read_text()
        tree = ast.parse(source)

        # Find all "from adcp... import X as LibraryX" statements
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("adcp"):
                for alias in node.names:
                    if alias.asname and alias.asname.startswith("Library"):
                        # e.g. "from adcp.types import Product as LibraryProduct"
                        # Local class name = alias.asname without "Library" prefix
                        local_name = alias.asname.removeprefix("Library")
                        # Import the actual library type
                        try:
                            mod = importlib.import_module(node.module)
                            lib_type = getattr(mod, alias.name, None)
                            if lib_type is not None and inspect.isclass(lib_type):
                                mapping[local_name] = lib_type
                        except (ImportError, AttributeError):
                            pass

    return mapping


# Library aliases whose local name is a plain re-export/alias, not a subclass.
ALIAS_ONLY_TYPES = {
    "AdCPBaseModel",
    "BrandManifest",
    "GetSignalsRequest",
    "PackageUpdate",
    "Property",
    "PromotedProducts",
    "ResponsePagination",
}

# Bases every schema in the package inherits. They are not a library type a class
# "narrows", so redefinition-grading must not treat them as one.
_UNIVERSAL_BASES = {"AdCPBaseModel"}


def _get_redefinition_targets() -> list[tuple[str, type, type]]:
    """Yield ``(local_name, local_cls, lib_base)`` for every local class that actually
    extends an imported ``Library*`` type.

    Membership is decided by the MRO, not by the class's NAME. The name-derived
    mapping above answers "which local class SHOULD extend LibraryX", which is the
    right question for the inheritance test but the wrong one for redefinition: a
    subclass whose name is not ``alias-minus-Library`` was never visited at all, so
    its redefinitions went ungraded and — worse — its allowlist entries read as
    *stale* rather than as unreachable. Three classes were invisible this way
    (AdCPPackageUpdate, SyncAccountsResponse, SyncCreativesResponse), carrying six
    live redefinitions between them.

    Bases that everything inherits (``AdCPBaseModel`` and the local base built on it)
    are excluded: they are not a "library type this class narrows", and treating them
    as one would flag every schema in the package.
    """
    mapping = _get_library_type_mapping()
    local_classes = _get_local_schema_classes()
    lib_bases = {lib for name, lib in mapping.items() if name not in _UNIVERSAL_BASES}

    targets: list[tuple[str, type, type]] = []
    for local_name, local_cls in sorted(local_classes.items()):
        if local_name in ALIAS_ONLY_TYPES:
            continue
        for base in inspect.getmro(local_cls)[1:]:
            if base in lib_bases and hasattr(base, "model_fields"):
                targets.append((local_name, local_cls, base))
                break
    return targets


def _get_local_schema_classes() -> dict[str, type]:
    """Get all classes defined in src.core.schemas (including submodules)."""
    schemas = importlib.import_module("src.core.schemas")
    classes = {}
    for name, obj in inspect.getmembers(schemas, inspect.isclass):
        # Include classes defined in the schemas package or its submodules
        if obj.__module__ and obj.__module__.startswith("src.core.schemas"):
            classes[name] = obj
    return classes


# Cache for AST-based field detection (parsed once)
_CLASS_OWN_FIELDS: dict[str, set[str]] | None = None


def _get_class_own_field_names(class_name: str) -> set[str]:
    """Get field names declared directly in a class body using AST.

    This avoids Pydantic's __annotations__ pollution where inherited fields
    appear on subclasses after model_rebuild().
    """
    import ast

    global _CLASS_OWN_FIELDS
    if _CLASS_OWN_FIELDS is None:
        _CLASS_OWN_FIELDS = {}
        for schemas_path in _get_schemas_source_files():
            source = schemas_path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    fields = set()
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            fields.add(item.target.id)
                    _CLASS_OWN_FIELDS[node.name] = fields

    return _CLASS_OWN_FIELDS.get(class_name, set())


class TestSchemaInheritance:
    """Every local schema class that has a Library* counterpart must inherit from it."""

    @pytest.mark.arch_guard
    def test_all_library_types_have_local_subclass(self):
        """For each Library* import, a local class with that name exists and inherits from it."""
        mapping = _get_library_type_mapping()
        local_classes = _get_local_schema_classes()

        # ALIAS_ONLY_TYPES (module scope) lists the Library* imports used as TypeAliases
        # or type hints rather than subclassed — legitimate, so no local subclass is due.
        violations = []
        for local_name, lib_type in sorted(mapping.items()):
            if local_name in ALIAS_ONLY_TYPES:
                continue

            local_cls = local_classes.get(local_name)
            if local_cls is None:
                # No local class with this name — might be used directly
                continue

            # Check MRO: local class must have library type in its inheritance chain
            mro = inspect.getmro(local_cls)
            if lib_type not in mro:
                violations.append(
                    f"{local_name} does not inherit from {lib_type.__module__}.{lib_type.__name__}. "
                    f"MRO: {[c.__name__ for c in mro]}"
                )

        assert not violations, "Schema classes not inheriting from their adcp library base:\n" + "\n".join(
            f"  - {v}" for v in violations
        )

    @pytest.mark.arch_guard
    def test_no_field_redefinition_in_subclasses(self):
        """Local subclasses should not redefine fields that exist in the library parent.

        Redefinition means the field was copied instead of inherited, which causes
        drift when the library updates the field's type or validator.

        Graded with ``assert_violations_match_allowlist`` so the allowlist can only
        SHRINK: an entry that stops being a real redefinition fails as stale instead
        of accumulating silently.
        """

        # Known exceptions: fields intentionally overridden with tighter types,
        # custom validators, nested serialization (Critical Pattern #4), or
        # exclude=True additions. Format: (ClassName, field_name)
        # Each override must have a documented reason. Do NOT add new entries
        # without verifying the override is intentional.
        KNOWN_OVERRIDES: set[tuple[str, str]] = {
            # Nested serialization overrides (Critical Pattern #4) —
            # Parent models re-declare list fields to use local subclass types
            ("CreateMediaBuyRequest", "packages"),
            ("GetMediaBuyDeliveryResponse", "aggregated_totals"),
            ("GetMediaBuyDeliveryResponse", "media_buy_deliveries"),
            ("GetSignalsResponse", "signals"),
            ("ListCreativesResponse", "pagination"),
            ("ListCreativesResponse", "query_summary"),
            ("ListCreativesResponse", "creatives"),
            ("PackageRequest", "targeting_overlay"),
            ("PackageRequest", "impressions"),
            ("PackageRequest", "creatives"),
            # Mirror of PackageRequest.targeting_overlay for the update path —
            # makes collection_list typed at the request boundary instead of
            # leaking through library extra="allow" as a raw dict.
            ("AdCPPackageUpdate", "targeting_overlay"),
            ("Placement", "format_ids"),
            ("Placement", "description"),
            ("QuerySummary", "filters_applied"),
            ("Signal", "signal_type"),
            ("Signal", "deployments"),
            # adcp 6.6 (spec 3.1.1) re-added status/changes/warnings/platform_id/assignment_errors/
            # assigned_to to the library sync_creatives_response Creative — status/platform_id/
            # assignment_errors/assigned_to are INHERITED (PR #1567). Internal review-routing
            # state was renamed to `internal_status` (a non-parent field, excluded from the wire).
            # changes/warnings/errors are deliberately REDECLARED with default_factory=list
            # (PR #1567 round-2 item 3): spec 3.1.1 types them `array`, and the parent's None default
            # serialized as null on the MCP structured_content path (bypasses model_dump strips).
            ("SyncCreativeResult", "changes"),
            ("SyncCreativeResult", "warnings"),
            ("SyncCreativeResult", "errors"),
            ("SyncCreativesRequest", "creatives"),
            ("SyncCreativesRequest", "push_notification_config"),
            # Creative overrides — listing base requires these fields, but we add
            # defaults for partial construction and override assets to untyped dict
            ("Creative", "name"),
            ("Creative", "status"),
            ("Creative", "created_date"),
            ("Creative", "updated_date"),
            ("Creative", "assets"),
            # Nested serialization — creative delivery uses local CreativeDeliveryData
            ("GetCreativeDeliveryResponse", "creatives"),
            # adcp 3.9 field overrides — library added fields we already had locally
            # with wider types (optional vs required) or salesagent-specific semantics
            ("CreateMediaBuyRequest", "account"),  # optional override (library requires it)
            ("CreativePolicy", "provenance_required"),  # custom description/default
            # GetMediaBuyDeliveryRequest: SDK 5.7 provides all fields; no local
            # redeclarations remain. Removed: account, attribution_window,
            # include_package_daily_breakdown, reporting_dimensions.
            ("GetProductsRequest", "buying_mode"),  # str|None override (library uses Literal discriminator)
            ("SyncCreativesRequest", "account"),  # optional override (library requires it)
            ("UpdateMediaBuyRequest", "end_time"),  # datetime|None (library uses AwareDatetime)
            ("UpdateMediaBuyRequest", "packages"),  # list[AdCPPackageUpdate] (local subclass type)
            ("UpdateMediaBuyRequest", "start_time"),  # datetime|Literal["asap"]|None (wider type)
            # adcp 4.3 field overrides — library made these required; we keep them
            # optional because identity is resolved at the transport boundary, and
            # required-key enforcement rolls out create_media_buy-first
            # (CreateMediaBuyRequest.idempotency_key now inherits the required field)
            ("Product", "reporting_capabilities"),  # optional override (not all products have it)
            ("SyncAccountsRequest", "idempotency_key"),  # optional override (required-key fast-follow)
            ("SyncCreativesRequest", "idempotency_key"),  # optional override (required-key fast-follow)
            ("UpdateMediaBuyRequest", "account"),  # optional override (resolved from identity)
            ("UpdateMediaBuyRequest", "idempotency_key"),  # optional override (required-key fast-follow)
            # Pattern #4: ListAccountsResponse.accounts uses local Account subclass
            ("ListAccountsResponse", "accounts"),
            # Pattern #4: the get_media_buys item chain. Both narrowings are load-bearing
            # — our Targeting adds ~30 fields the library's TargetingOverlay lacks, and
            # serializing through the library annotation would drop them.
            #
            # Note what is NOT here, and why, because the two reasons are different:
            #   snapshot, creative_approvals — local SUBCLASSES that add no fields, so
            #     they inherit the parent's declaration outright.
            #   snapshot_unavailable_reason, approval_status — not subclasses at all.
            #     Their types are plain ALIASES of the library enums
            #     (SnapshotUnavailableReason, ApprovalStatus), so there is no local
            #     declaration for this guard to see in the first place. Aliasing is what
            #     stopped the members drifting; the local SnapshotUnavailableReason copy
            #     had lost one of the pinned three.
            ("GetMediaBuysPackage", "targeting_overlay"),
            ("GetMediaBuysMediaBuy", "packages"),
            ("GetMediaBuysResponse", "media_buys"),
            # Required-field tightening (#1399 Plan-B): pinned 3.1 marks these
            # success-arm fields required; the SDK base declares them optional, so
            # we redeclare required to match the spec.
            ("GetProductsResponse", "products"),
            # Pattern #4 on the two sync success arms. Both narrow the parent's item
            # type to a local subclass that adds fields the library type lacks
            # (SyncResponseAccount; SyncCreativeResult's assigned_to /
            # assignment_errors), so serializing through the parent annotation would
            # drop them. Newly VISIBLE rather than newly introduced: the collector
            # keyed on alias-minus-"Library" until now, and neither class's name
            # matches its parent's, so neither was ever visited.
            ("SyncAccountsResponse", "accounts"),
            ("SyncCreativesResponse", "creatives"),
        }

        found: set[tuple[str, str]] = set()
        for local_name, _local_cls, lib_base in _get_redefinition_targets():
            # Fields declared DIRECTLY on the local class. Can't use __annotations__ —
            # Pydantic model_rebuild populates it with inherited fields — so read
            # source-level declarations out of the AST.
            own = _get_class_own_field_names(local_name)
            found |= {(local_name, field) for field in own & set(lib_base.model_fields.keys())}

        assert_violations_match_allowlist(
            found,
            KNOWN_OVERRIDES,
            fix_hint=(
                "A new violation means a field was copied instead of inherited — delete the "
                "redeclaration, or add it to KNOWN_OVERRIDES with the reason it must differ. "
                "A stale entry means the redeclaration is gone (delete the entry) OR that the "
                "class stopped being collected — check it is still reachable from "
                "_get_redefinition_targets before assuming it was fixed."
            ),
        )
