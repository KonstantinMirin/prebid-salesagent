"""Every registered tool's response schema must be found BY CATEGORY, never by bare filename.

``tests/helpers/response_schemas._category`` derives a response schema's directory
from the SDK's own domain tree, and ``response_schema_ref`` qualifies the filename
with it. When that derivation returns nothing, the ref degrades to a bare basename
and the loader searches the whole pinned tree for it — which SILENTLY WORKS right up
to the first basename that exists in two categories, and then refuses.

That is exactly how adcp 9.0.0 landed. The derivation read the flat ``adcp.types``
namespace, where v9 shadowed six of the registry's response names with
``adcp.types.canonical_creative`` copies and renamed a seventh
(``ListCreativeFormatsResponse`` -> ``LegacyListCreativeFormatsResponse``, the tool
being deprecated in AdCP 3.2). All seven lost their category. Six kept passing,
because their basenames are unique and the bare-filename search happened to land on
the right file. The seventh, ``list-creative-formats-response.json``, is the one
basename that genuinely collides — ``creative/`` (titled "List Creative Formats
Response (Creative Agent)") and ``media-buy/`` — so the loader refused it and 413
BDD scenarios failed with one message.

THE SIX THAT KEPT PASSING ARE WHAT THIS GUARD IS FOR. A bare-filename resolution
that lands on the right file is graded by accident, and nothing reports it. So a
bare ref is a FAILURE here even when it loads: the assertion is that the category
was DERIVED, not that the schema was eventually found.

Scope note: this grades the derivation, not the schema contents. Whether
``media-buy/list-creative-formats-response.json`` is the right contract for this
seller is a spec question, answered where the ref is consumed.
"""

from __future__ import annotations

import pytest

from src.core.tools.registry import TOOLS
from tests.helpers.pinned_schema import load
from tests.helpers.response_schemas import _camel, _category, _response_owners, response_schema_ref

#: Tools the pinned AdCP tree does not describe at all, with the reason. These have no
#: SDK response type under ANY spelling, so there is no domain package to read a category
#: off and no category to derive — unlike the v9 regression, where the type existed and
#: the derivation was looking in the wrong place.
#:
#: May only SHRINK. A tool listed here that starts resolving is caught below as a stale
#: entry; a tool that stops resolving gets the derivation fixed, never a row here.
_NO_PINNED_RESPONSE = {
    "complete_task": (
        "Seller-specific tool, absent from the pinned AdCP 3.2 tree entirely: no "
        "CompleteTaskResponse in adcp.types, in adcp.types.domains.*, or under a Legacy* "
        "spelling, and no complete-task-response.json in the SDK tree. Its schemas are "
        "app-owned under tests/helpers/adcp_pinned_schema.app_schema_root() (schemas/ at "
        "the repo root), where a bare filename is unambiguous because that tree is flat. "
        "Not a derivation defect and not a DTO/public-name mismatch — the registry row "
        "spells CompleteTaskRequest, which is the name the SDK would use if it had one."
    ),
}


@pytest.mark.parametrize("tool", sorted(set(TOOLS) - set(_NO_PINNED_RESPONSE)))
def test_response_schema_ref_is_category_qualified(tool: str):
    """The ref must carry a derived category, and that ref must load.

    Both halves matter and neither implies the other. A bare ref can load (six tools
    did, through all of adcp 9.0.0's regression) and a qualified ref could name a
    directory that is not there.
    """
    category = _category(tool)
    assert category is not None, (
        f"{tool}: no schema category could be derived. {_camel(tool)}Response is declared "
        f"by no package under adcp.types.domains, so response_schema_ref() falls back to "
        f"the bare filename {tool.replace('_', '-')}-response.json and the loader searches "
        f"the whole pinned tree for it. That resolves by luck until the basename collides. "
        f"Fix the derivation in tests/helpers/response_schemas._response_owners — do not add "
        f"a row to _NO_PINNED_RESPONSE, which is only for tools the pinned tree omits."
    )

    ref = response_schema_ref(tool)
    assert ref == f"{category}/{tool.replace('_', '-')}-response.json", (
        f"{tool}: derived category {category!r} but the ref is {ref!r}"
    )
    load(ref)  # PinnedSchemaError if the derived category names nothing


@pytest.mark.parametrize(("tool", "reason"), sorted(_NO_PINNED_RESPONSE.items()))
def test_no_pinned_response_entries_are_not_stale(tool: str, reason: str):
    """An allowlisted tool that acquires a pinned response type loses its row.

    Without this, a spec release that adds the tool leaves it permanently exempt from
    the check above — the allowlist outliving its reason is how it stops shrinking.
    """
    assert tool in TOOLS, f"{tool} is no longer a registered tool; drop its _NO_PINNED_RESPONSE row"
    assert reason.strip(), f"{tool}: _NO_PINNED_RESPONSE rows must carry a reason"
    assert not _response_owners(tool), (
        f"{tool}: {_camel(tool)}Response is now declared by {_response_owners(tool)}, so the "
        f"pinned tree describes this tool and its category derives. Remove its "
        f"_NO_PINNED_RESPONSE row so the category check covers it."
    )


def test_two_domains_declaring_one_response_name_raises(monkeypatch):
    """Ambiguity must REFUSE, not resolve to whichever package sorts first.

    This is the failure mode the v9 regression was a mild version of: a category
    picked by accident grades a seller against a contract that is not theirs, and
    looks green doing it. ``list_creative_formats`` is the realistic shape — two
    schemas, two actors ("(Creative Agent)" vs the media-buy seller), one basename —
    so the refusal is graded here rather than left to be discovered.
    """
    import adcp.types.domains as adcp_domains

    # get_products is declared by media_buy alone; pretend creative declares it too.
    assert _response_owners("get_products") == ("media_buy",), (
        "fixture assumption broke: get_products is no longer media_buy-only"
    )
    import adcp.types.domains.creative as creative_domain

    monkeypatch.setattr(creative_domain, "GetProductsResponse", object, raising=False)
    monkeypatch.setattr(adcp_domains, "DOMAINS", ("creative", "media_buy"), raising=False)
    _response_owners.cache_clear()
    try:
        with pytest.raises(ValueError, match="declared by 2 domain packages"):
            _category("get_products")
    finally:
        _response_owners.cache_clear()
