"""Which pinned AdCP request schema each registered tool's request implements.

The ONE binding of tool name -> pinned request schema. Two suites grade against
it and they must grade against the SAME binding:

* ``tests/unit/test_pydantic_schema_alignment.py`` -- the request DTO's declared
  and advertised fields, graded against the schema's ``properties``.
* ``tests/unit/test_request_factory_schema_conformance.py`` -- the request
  FACTORY's baseline payload, graded against the whole schema.

A second copy of this map is the copy-paste-with-variable-substitution shape
CLAUDE.md's DRY invariant refuses, and the cost is not hypothetical: the
alignment suite's own history records that ``list_accounts`` went ungraded
precisely because a second, differently-constrained table decided membership.
The two suites ask different questions of the same binding; the binding itself
is one fact about the spec.
"""

from __future__ import annotations

#: Registered tool -> the pinned request schema its DTO implements. Keyed by TOOL rather
#: than by model because the tool registry is what the coverage tests read: a request
#: DTO that quietly stops being graded is the failure this pairing exists to prevent, and a
#: model-keyed map cannot notice a tool it was never given.
#:
#: Not the same table as the alignment suite's SCHEMA_TO_MODEL_MAP, which drives three OTHER
#: test classes whose membership is constrained by unrelated history (CreateMediaBuyRequest is
#: held out of it pending brand_card). Merging them would couple this grading to that
#: hold-out, which is exactly how list_accounts -- the tool with the one declared departure --
#: went ungraded.
#:
#: list_creative_formats resolves to the media-buy/ copy, not the creative/ one: the pinned
#: tree ships BOTH, they differ (creative/ has account, include_pricing, type; media-buy/ has
#: property_id, publisher_domain), and media-buy/ is the path the generated BR-UC-005
#: storyboards cite at the pinned commit. Picking the other one grades this tool against a
#: schema nothing else in the repo uses.
REQUEST_SCHEMA_BY_TOOL: dict[str, str] = {
    "create_media_buy": "media-buy/create-media-buy-request.json",
    "get_adcp_capabilities": "protocol/get-adcp-capabilities-request.json",
    "get_media_buy_delivery": "media-buy/get-media-buy-delivery-request.json",
    "get_media_buys": "media-buy/get-media-buys-request.json",
    "get_products": "media-buy/get-products-request.json",
    "get_task": "protocol/get-task-status-request.json",
    "list_accounts": "account/list-accounts-request.json",
    "list_creative_formats": "media-buy/list-creative-formats-request.json",
    "list_creatives": "creative/list-creatives-request.json",
    "list_tasks": "protocol/list-tasks-request.json",
    "sync_accounts": "account/sync-accounts-request.json",
    "sync_creatives": "creative/sync-creatives-request.json",
    "update_media_buy": "media-buy/update-media-buy-request.json",
}

#: Tools AdCP 3.1.1 does not define, so there is no pinned request schema to grade them
#: against. This is a statement about the SPEC, not an exemption granted here, and the
#: coverage test PROVES each entry by showing the pinned tree really resolves no request
#: schema under that name. Rebasing any of them onto a spec task (update_performance_index is
#: the spec's provide_performance_feedback under an older name) moves it into the map above;
#: the set only shrinks.
TOOLS_WITH_NO_PINNED_REQUEST_SCHEMA = frozenset(
    {"complete_task", "list_authorized_properties", "update_performance_index"}
)
