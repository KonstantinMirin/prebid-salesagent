"""Which pinned AdCP request schema a registered tool's request DTO implements — DERIVED.

This file used to hold ``REQUEST_SCHEMA_BY_TOOL``, thirteen hand-written rows of
tool -> schema path, and its own docstring argued that the binding is ONE fact about
the spec that no second table may re-state. That argument was right about the second
table and wrong about the first: a hand-written row is a copy too, and the thing it
copies is already written down in the artifact. ``adcp``'s generated request types are
one module per pinned schema file, named after it — ``create_media_buy_request`` for
``media-buy/create-media-buy-request.json`` — so a DTO grounded in the SDK vocabulary
already NAMES the schema it implements, in the only place that cannot drift from it.

So the rule is:

* A DTO whose ancestry reaches an ``adcp`` generated request type takes that type's
  module path as its schema ref. Twelve of the thirteen rows resolved this way, byte
  for byte, including ``list_creative_formats`` -> ``media-buy/`` rather than
  ``creative/`` — the one row the old table argued for at length, now answered by the
  SDK instead of by a comment.
* A DTO with no such ancestry, or one whose schema is named differently from its type,
  declares :data:`~src.core.schemas._base.WireSerializerMixin._PINNED_SCHEMA_REF`
  ITSELF. ``GetTaskRequest`` is the only live case: the tool is ``get_task`` and the
  schema is ``protocol/get-task-status-request.json``, which no derivation from either
  name produces.

WHAT MUST NOT BE LOST, and is not
---------------------------------
The old table was keyed by TOOL, not by model, and its docstring defended that: "a
request DTO that quietly stops being graded is the failure this pairing exists to
prevent, and a model-keyed map cannot notice a tool it was never given." That property
is the requirement, and the table was only one way to meet it. It is met here MORE
strongly, because membership is no longer a key set anyone can decline to add to:
callers parametrize over :func:`graded_request_schemas`, whose tool set comes from the
LIVE MCP registry, and
``TestNoNonSpecFieldsAreAdvertised::test_every_registered_tool_is_graded_or_provably_has_no_spec_schema``
requires every registered tool that resolves NO ref to PROVE the pinned tree holds no
request schema for it — see :func:`pinned_request_schema_candidates`.

That proof also got stronger. The version this replaces probed exactly one candidate
filename, ``<tool-name>-request.json``; ``get_task``'s schema is
``get-task-status-request.json``, so had its binding ever been dropped the probe would
have found nothing and reported the tool as legitimately ungraded. The candidate search
here is token-subset, so it finds that file and fails.
"""

from __future__ import annotations

from pydantic import BaseModel

from tests.helpers import pinned_schema

#: The package every generated SDK request/response type lives under, one module per
#: pinned schema file. ``adcp.types.generated_poc.media_buy.create_media_buy_request``
#: is ``media-buy/create-media-buy-request.json``: the two components after this marker
#: are the schema's category directory and its file stem, with ``_`` for the ``-`` a
#: Python module name cannot carry.
_GENERATED_PACKAGE = "generated_poc."


def _ref_from_generated_module(module: str) -> str | None:
    """The pinned schema ref a generated SDK type's module path names, if it names one."""
    _, marker, tail = module.partition(_GENERATED_PACKAGE)
    if not marker:
        return None
    category, _, stem = tail.partition(".")
    if not category or not stem:
        return None
    return f"{category.replace('_', '-')}/{stem.replace('_', '-')}.json"


def pinned_request_schema_ref(model: type[BaseModel]) -> str | None:
    """The pinned request schema *model* implements, or None when it implements none.

    A ref the DTO declares on ``_PINNED_SCHEMA_REF`` wins over the derivation: the
    declaration exists for the case the derivation cannot reach (a schema named
    differently from its type, or a DTO with no SDK ancestry at all), so a derivation
    that overrode it would make the declaration unreachable.

    Note that a REQUEST DTO declaring ``_PINNED_SCHEMA_REF`` changes no serialization
    behaviour: the attribute drives ``_always_include_null_fields`` only for classes
    that inherit :class:`WireSerializerMixin`, and no request DTO does. On a request
    model it is purely the slot's other half — "the schema I am graded against".
    """
    declared = getattr(model, "_PINNED_SCHEMA_REF", None)
    if declared:
        return str(declared)
    from src.core.tools._announced_shape import sdk_grounding

    grounding = sdk_grounding(model)
    if grounding is None:
        return None
    return _ref_from_generated_module(grounding.__module__)


def graded_request_schemas() -> dict[str, tuple[str, type[BaseModel]]]:
    """``tool -> (schema ref, request DTO)`` for every registered tool that resolves one.

    The tool set is the LIVE MCP registry, so a tool cannot sit outside the grading by
    being left out of something. A tool that resolves no ref is absent here and is
    graded instead by the coverage test, which makes it prove the spec defines no
    request schema for it.
    """
    from tests.helpers.registered_tools import registered_request_dtos

    graded = {}
    for tool_name, model in registered_request_dtos().items():
        ref = pinned_request_schema_ref(model)
        if ref is not None:
            graded[tool_name] = (ref, model)
    return graded


def pinned_request_schema_candidates(tool_name: str) -> dict[str, str]:
    """``ref -> reason`` for every pinned request schema that plausibly belongs to *tool_name*.

    The negative proof behind "this tool genuinely has no pinned request schema". A
    schema qualifies when its file stem's words are a SUPERSET of the tool name's --
    ``get-task-status`` for ``get_task`` -- which is what catches a schema whose name
    carries extra words the tool name does not. An exact-filename probe does not:
    ``get_task`` -> ``get-task-request.json`` resolves nothing, and reporting that as
    "no schema exists" is how a tool goes silently ungraded.

    ``bundled/`` is skipped: it is a physical mirror of the plain tree (see
    ``tests.helpers.pinned_schema``), so including it reports every hit twice.
    """
    wanted = set(tool_name.split("_"))
    root = pinned_schema.schema_root()
    return {
        f"{path.parent.name}/{path.name}": f"stem {path.stem!r} covers {sorted(wanted)}"
        for path in sorted(root.rglob("*-request.json"))
        if "bundled" not in path.relative_to(root).parts and wanted <= set(path.stem.split("-"))
    }
