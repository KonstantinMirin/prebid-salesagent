"""``tool -> its response schema``, derived rather than written down.

A BDD scenario names the TOOL and, where the schema branches, the branch. It
never names a schema file: a filename in a feature file is a second spelling of
"which tool is this scenario exercising", and the two drift.

Everything here is derived from two live sources — the tool registry and the
pinned SDK's own domain tree — so a tool cannot be graded against the wrong
contract by anyone forgetting to update a table.

``tests/unit/test_response_schema_category_resolves.py`` grades that derivation,
and grades a BARE-FILENAME resolution as a failure even when it loads. Without
it, a derivation that silently stops working goes unreported for as long as the
basenames it falls back to happen to be unique — which is exactly what adcp
9.0.0 did to six of these tools.
"""

from __future__ import annotations

import importlib
from functools import cache

from adcp.types import domains as adcp_domains

from src.core.tools.registry import TOOLS
from tests.helpers.pinned_schema import load, validator_for


def _camel(tool: str) -> str:
    return "".join(part.title() for part in tool.split("_"))


@cache
def _response_owners(tool: str) -> tuple[str, ...]:
    """Every ``adcp.types.domains`` package that DECLARES *tool*'s response type.

    THE DOMAIN TREE IS THE SOURCE, NOT THE FLAT ``adcp.types`` NAMESPACE, and the
    SDK says why in ``adcp/types/domains/__init__.py``: codegen writes that tree
    "in that layout and defines every class here, so a type name more than one
    schema declares is unambiguous BY PATH rather than by a mangled name". The
    category this module needs IS that path, so it asks the tree that carries it.

    The flat namespace cannot answer. It is one `dir()` with every domain's names
    collapsed into it, so a name two schemas declare arrives mangled — and the
    mangling is not a stable convention this module could follow. Measured
    against adcp 9.0.0, the flat ``*Response`` name reaches a module with no
    category for six of the registry's tools (``get_products``,
    ``get_media_buys``, ``get_media_buy_delivery``, ``list_creatives``,
    ``create_media_buy``, ``update_media_buy`` all land in
    ``adcp.types.canonical_creative``) and does not exist at all for a seventh
    (``list_creative_formats``, renamed ``LegacyListCreativeFormatsResponse``
    because the tool is deprecated in AdCP 3.2). Reading the flat name left all
    seven with no category, and only ``list_creative_formats`` FAILED for it —
    its basename is the one that genuinely collides across two categories, so the
    loader refused it. The other six fell back to a bare filename that happened
    to hit the right file. Graded by accident is the state this function exists to
    prevent, and the next colliding basename is when it stops being lucky.

    Returns empty for a tool the SDK does not type at all. ``complete_task`` is
    the live case — seller-specific, absent from the pinned tree entirely, its
    schemas app-owned under ``app_schema_root()`` and found by bare filename,
    which is unambiguous there.
    """
    name = _camel(tool) + "Response"
    return tuple(
        domain
        for domain in adcp_domains.DOMAINS
        if getattr(importlib.import_module(f"{adcp_domains.__name__}.{domain}"), name, None) is not None
    )


def _category(tool: str) -> str | None:
    """The schema's directory, read off the domain package that declares the response.

    ``GetProductsResponse`` is declared in ``adcp.types.domains.media_buy``, and
    its schema lives in ``media-buy/``. The package name IS the directory, so
    there is nothing to translate beyond the underscore.

    Qualifying the ref is not decoration: two DIFFERENT schemas share the
    basename ``list-creative-formats-response.json`` (one under ``creative/``,
    titled "(Creative Agent)", one under ``media-buy/``), so a bare filename is
    genuinely ambiguous there and the loader refuses it rather than guessing.

    Two domains declaring one response name RAISES rather than picking the first.
    Choosing between two live categories is the guess this module exists to not
    make, and a wrong one grades a seller against another actor's contract while
    looking perfectly green.
    """
    owners = _response_owners(tool)
    if not owners:
        return None
    if len(owners) > 1:
        raise ValueError(
            f"{tool}: {_camel(tool)}Response is declared by {len(owners)} domain packages "
            f"({', '.join(owners)}), so its schema category is ambiguous. Pick the one the "
            f"pinned schema for this seller's response actually lives under and say so here; "
            f"do not let this resolve to whichever package sorts first."
        )
    return owners[0].replace("_", "-")


def response_schema_ref(tool: str) -> str:
    """The schema ref for *tool*'s response, category-qualified where one exists.

    REGISTRY MEMBERSHIP IS REQUIRED, and the failure is the point. A tool this
    seller has not built cannot be dispatched, so no response exists to grade —
    a scenario naming one is not a scenario that could pass. Resolving its schema
    anyway would let such a scenario look gradeable while exercising nothing,
    which is how a whole use case quietly stops counting.

    ``activate_signal``, ``build_creative``, ``preview_creative`` and the ``si_*``
    session tools all have pinned schemas and no implementation. Raising here
    names them, one scenario at a time, and that count IS the scale of what is
    left to build.
    """
    if tool not in TOOLS:
        raise KeyError(
            f"{tool!r} is not a registered tool, so nothing can dispatch it and no "
            f"response exists to grade. The registry (src/core/tools/registry.py) "
            f"holds: {sorted(TOOLS)}"
        )
    filename = tool.replace("_", "-") + "-response.json"
    category = _category(tool)
    return f"{category}/{filename}" if category else filename


def branch_names(tool: str) -> list[str]:
    """The ``oneOf`` branch words a scenario may name, e.g. success/error/submitted.

    Read from the schema's own branch titles: ``CreateMediaBuySuccess`` under
    ``create-media-buy-response.json`` yields ``"success"``. Empty for a tool
    whose response is one shape.
    """
    schema = load(response_schema_ref(tool))
    prefix = _camel(tool)
    words = []
    for branch in schema.get("oneOf") or schema.get("anyOf") or []:
        title = branch.get("title", "")
        words.append((title[len(prefix) :] if title.startswith(prefix) else title).lower())
    return [w for w in words if w]


def response_validator(tool: str, branch: str | None = None):
    """A validator for *tool*'s response, narrowed to one branch if named.

    Naming a branch on a BRANCHLESS tool stays an error — there is no such
    contract to narrow to, so the sentence is about a tool the author is
    misremembering.

    Omitting the branch on a BRANCHING tool is allowed, and validates the whole
    ``oneOf``. That reads like a weaker check than it is, so it was measured
    against ``create-media-buy-response.json`` before being permitted: an empty
    object, an object of junk keys, a success document missing ``confirmed_at``
    and ``revision``, a submitted document missing ``task_id``, and a success
    document whose ``status`` is misspelled are ALL rejected. "One of the legal
    shapes" excludes essentially every malformed response.

    It exists for the SCENARIO OUTLINE, where the branch is a column: 104
    scenarios end in ``the result should be <outcome>`` and a single outline
    carries both ``Examples: Valid partitions`` and ``Examples: Invalid
    partitions``. One line in that outline CANNOT name a branch that is right
    for every row. Refusing here would leave those scenarios with no compliance
    check at all, which is the outcome the rule exists to prevent.

    Prefer the branch form wherever the scenario pins ONE outcome — it is
    strictly stronger, and the general form would accept the branch the
    scenario asserts did NOT happen.
    """
    ref = response_schema_ref(tool)
    available = branch_names(tool)

    if branch is None:
        return validator_for(ref)

    if branch not in available:
        raise ValueError(
            f"{tool} has no {branch!r} response branch. "
            f"{'Available: ' + str(available) if available else 'It responds in one shape — drop the branch word.'}"
        )

    schema = load(ref)
    for candidate in schema.get("oneOf") or schema.get("anyOf") or []:
        title = candidate.get("title", "")
        if (title[len(_camel(tool)) :] if title.startswith(_camel(tool)) else title).lower() == branch:
            return validator_for(f"{ref}#/oneOf/{(schema.get('oneOf') or []).index(candidate)}")
    raise ValueError(f"{tool}: branch {branch!r} vanished between listing and lookup")
