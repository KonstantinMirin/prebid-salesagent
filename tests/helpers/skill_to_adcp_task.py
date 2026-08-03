"""Single source of truth for A2A skill-name -> AdCP-task-name resolution.

salesagent-1q8d.1 (PR #1838 review R1-10 measurement): two independent copies
of this map existed — ``A2AAdCPValidator.SKILL_TO_SCHEMA_MAP`` in
tests/integration/test_a2a_skill_invocation.py and a local ``skill_to_schema``
dict inside ``A2AAdCPComplianceClient.validate_skill_response`` in
tests/e2e/test_a2a_adcp_compliance.py — and had drifted (``approve_creative``
resolved to a schema name in one, ``None`` in the other).

``approve_creative`` and ``add_creative_assets`` map to ``None``: no such task
exists anywhere in the pinned AdCP index (verified by
tests/e2e/test_skill_to_adcp_task_map.py, which also pins every non-None entry
here against the pinned index).
"""

from __future__ import annotations

SKILL_TO_ADCP_TASK: dict[str, str | None] = {
    "get_products": "get-products",
    "create_media_buy": "create-media-buy",
    "update_media_buy": "update-media-buy",
    "get_media_buy_delivery": "get-media-buy-delivery",
    "sync_creatives": "sync-creatives",
    "list_creatives": "list-creatives",
    # Skills without a corresponding AdCP task in the pinned index yet.
    "approve_creative": None,
    "add_creative_assets": None,
    "get_media_buy_status": None,
    "optimize_media_buy": None,
}
