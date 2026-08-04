"""Validate/load AdCP JSON schemas from the installed adcp SDK's pinned tree,
fully offline.

Single source of truth for schema-shape assertions in tests (e.g. the BDD
step "the response should be schema-valid against <file>") AND for the
Pydantic-model alignment suite's schema walking
(tests/unit/test_pydantic_schema_alignment.py). Reads the SDK's own "plain"
schema tree (``adcp/_schemas/<major.minor>/``, sibling of the SDK's
``bundled/`` tree) — never the network, and never an independently vendored
snapshot: the SDK's own installed version IS the pin (moves with
pyproject.toml's ``adcp`` version), so there is exactly one upstream pin for
every consumer that reads through this module (this module previously read
a separately vendored, independently pinned fixture tree that had already
drifted a full spec-minor behind).

The plain tree (not ``bundled/``) is deliberately the source: ``bundled/``
only physically ships 8 of the SDK's 16 top-level schema categories (no
``account/``, ``enums/``, ``governance/``, etc.) — it is a strict subset of
the plain tree, not a superset, despite being individually self-contained
per file. The plain tree's schemas use relative ``$ref``s (``../core/x.json``,
resolved against the referring file's own directory) instead of bundled's
pre-inlined local anchors; this module resolves those relative refs by
giving every loaded schema a synthetic, deterministic ``$id`` (an
``https://`` URI mirroring its path under the schema root) before handing it
to ``jsonschema``/``referencing`` — a plain ``adcp:///...``-style custom
scheme silently fails ``referencing``'s ``urljoin``-based resolution, so the
synthetic ``$id`` MUST be http(s)-shaped.

Two surfaces, matching the two distinct things callers need:

- ``validator_for(ref)`` — a ready-to-use ``Draft7Validator`` with full
  ``$ref`` resolution wired, for validating a payload against a schema
  (``validate_against_pinned_schema`` is the convenience wrapper most
  callers want).
- ``load(ref)`` — a single schema's raw dict, ``$ref``s left as-is, for
  callers that WALK the schema tree themselves (the alignment suite's
  synthetic-example generator) rather than validating a concrete payload.
  ``load`` does NOT resolve nested refs; use ``resolve_ref`` to follow one.

A missing schema (the SDK layout changed, or a ``$ref`` is outside the
resolvable tree) is a HARD FAILURE, never a silent skip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import referencing
from jsonschema.validators import Draft7Validator
from referencing.jsonschema import DRAFT7

from tests.helpers.sdk_schema_root import sdk_schema_root

# Every loaded schema gets a synthetic $id under this prefix, mirroring its
# path relative to the schema root, so relative $refs resolve deterministically.
_SYNTHETIC_BASE_URI = "https://adcp.internal/schemas/"

# The SDK's bundled/ subtree pre-inlines a partial (8-of-16-category) mirror
# of the plain tree under the same filenames — searching it too would make
# every mirrored bare filename ambiguous (e.g. "list-creatives-response.json"
# exists at both creative/list-creatives-response.json and
# bundled/creative/list-creatives-response.json). Bare-filename lookups are
# scoped to the plain tree only; bundled/ is never read by this module.
_EXCLUDED_TOP_LEVEL_DIR = "bundled"


def _schema_root() -> Path:
    return sdk_schema_root()


def _uri_for_path(path: Path) -> str:
    rel = path.relative_to(_schema_root())
    return _SYNTHETIC_BASE_URI + str(rel).replace("\\", "/")


def _path_for_uri(uri: str) -> Path:
    if not uri.startswith(_SYNTHETIC_BASE_URI):
        raise AssertionError(f"Unexpected schema URI (expected {_SYNTHETIC_BASE_URI}...): {uri!r}")
    rel = uri[len(_SYNTHETIC_BASE_URI) :]
    path = _schema_root() / rel
    if not path.exists():
        raise AssertionError(f"Pinned schema not found: {uri} -> {path}")
    return path


def _resolve_filename(filename: str) -> Path:
    """Resolve a bare or category-qualified schema filename to its path.

    A bare filename (``"list-creatives-response.json"``) is searched across
    the plain schema tree (``bundled/`` excluded — see module docstring). If
    that search is still ambiguous (a true same-basename collision within
    the plain tree itself, e.g. ``core/error.json`` vs
    ``trusted-match/error.json``), this raises rather than silently picking
    one — pass a category-qualified ref (``"core/error.json"``) instead.
    """
    root = _schema_root()
    if "/" in filename:
        path = (root / filename).resolve()
        # Containment check BEFORE the filesystem probe: a category-qualified
        # ref can embed traversal (e.g. "media-buy/../../../../etc/hosts"),
        # and a bare .exists() on an unresolved path lets the OS follow the
        # ".." segments — silently reading outside the schema tree.
        if not path.is_relative_to(root.resolve()):
            raise AssertionError(f"Schema ref {filename!r} escapes the pinned SDK schema tree: {path}")
        if not path.exists():
            raise AssertionError(f"Pinned schema not found: {filename} -> {path}")
        return path

    matches = sorted(p for p in root.rglob(filename) if _EXCLUDED_TOP_LEVEL_DIR not in p.relative_to(root).parts)
    if not matches:
        raise AssertionError(f"Pinned schema {filename!r} not found under {root}.")
    if len(matches) > 1:
        rels = [str(m.relative_to(root)) for m in matches]
        raise AssertionError(
            f"Pinned schema filename {filename!r} is ambiguous ({rels}) — pass a "
            f"category-qualified ref (e.g. {rels[0]!r}) instead of a bare filename."
        )
    return matches[0]


def _load_with_synthetic_id(path: Path) -> dict[str, Any]:
    """Load a schema file, stamping a synthetic $id so its relative $refs
    (and any $refs INTO it from a sibling schema) resolve deterministically."""
    schema = json.loads(path.read_text())
    return {**schema, "$id": _uri_for_path(path)}


def load(ref: str) -> dict[str, Any]:
    """Load one schema's raw dict (bare or category-qualified filename).

    $refs inside the returned dict are left as-is (relative, e.g.
    ``"../core/duration.json"``) — this is for callers that walk the schema
    tree themselves. Use ``resolve_ref`` to follow a $ref found this way.
    """
    return _load_with_synthetic_id(_resolve_filename(ref))


def resolve_ref(ref: str, *, from_path: Path) -> dict[str, Any]:
    """Resolve a $ref string found INSIDE the schema loaded from from_path
    (relative to that schema's own directory) to its raw dict."""
    target = (from_path.parent / ref.split("#", 1)[0]).resolve()
    root = _schema_root().resolve()
    if not target.is_relative_to(root):
        raise AssertionError(f"$ref {ref!r} (from {from_path}) resolves outside the schema root: {target}")
    return _load_with_synthetic_id(target)


def _canonicalize_refs(node: Any, *, file_dir: Path, root: Path) -> Any:
    """Recursively rewrite every "$ref" string in *node* from a path relative
    to file_dir (the schema file's own directory — the plain tree's ``$ref``
    convention) to a path relative to root (this module's root-relative
    convention, understood by ``load``/``resolve_filename``/bare filenames)."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                target_part, _, fragment = value.partition("#")
                target = (file_dir / target_part).resolve()
                rel = str(target.relative_to(root)).replace("\\", "/")
                out[key] = rel + (f"#{fragment}" if fragment else "")
            else:
                out[key] = _canonicalize_refs(value, file_dir=file_dir, root=root)
        return out
    if isinstance(node, list):
        return [_canonicalize_refs(item, file_dir=file_dir, root=root) for item in node]
    return node


def load_canonicalized(ref: str) -> dict[str, Any]:
    """Load one schema's raw dict with every ``$ref`` inside it rewritten to
    be root-relative (e.g. ``"../core/duration.json"`` found in
    ``media-buy/get-products-request.json`` becomes ``"core/duration.json"``).

    For callers that walk the schema tree themselves (the alignment suite's
    synthetic-example generator) and recursively re-call ``load_canonicalized``
    on every ``$ref`` they encounter — this makes every ref they see
    resolvable the same way regardless of how deep the schema that
    contained it was nested, without threading a "current file" context
    through the walk.
    """
    path = _resolve_filename(ref)
    schema = _load_with_synthetic_id(path)
    return _canonicalize_refs(schema, file_dir=path.parent, root=_schema_root())


def _retrieve(uri: str) -> referencing.Resource:
    return DRAFT7.create_resource(_load_with_synthetic_id(_path_for_uri(uri)))


def validator_for(ref: str) -> Draft7Validator:
    """A Draft7Validator for *ref* with full (relative) $ref resolution wired."""
    path = _resolve_filename(ref)
    schema = _load_with_synthetic_id(path)
    registry: referencing.Registry = referencing.Registry(retrieve=_retrieve)
    registry = registry.with_resource(schema["$id"], DRAFT7.create_resource(schema))
    return Draft7Validator(schema, registry=registry)


def validate_against_pinned_schema(filename: str, data: Any) -> None:
    """Assert *data* is schema-valid against the pinned AdCP schema *filename*.

    Raises ``AssertionError`` listing every JSON-path violation on failure.
    """
    validator = validator_for(filename)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        details = "\n".join(
            f"  at {'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        )
        raise AssertionError(f"Response is not schema-valid against {filename}:\n{details}")
