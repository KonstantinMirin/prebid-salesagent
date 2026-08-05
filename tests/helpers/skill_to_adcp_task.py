"""Single source of truth for A2A skill-name -> AdCP-task-name resolution.

salesagent-1q8d.1 (PR #1838): two independent copies
of this map existed — ``A2AAdCPValidator.SKILL_TO_SCHEMA_MAP`` in
tests/integration/test_a2a_skill_invocation.py and a local ``skill_to_schema``
dict inside ``A2AAdCPComplianceClient.validate_skill_response`` in
tests/e2e/test_a2a_adcp_compliance.py — and had drifted (``approve_creative``
resolved to a schema name in one, ``None`` in the other).

``approve_creative``, ``add_creative_assets``, ``get_media_buy_status``,
``optimize_media_buy``, and ``list_authorized_properties`` map to ``None``:
no such task exists anywhere in the pinned AdCP index (verified by
tests/e2e/test_skill_to_adcp_task_map.py, which also pins every non-None entry
here against the pinned index).

salesagent-1zq3.28 (R3-28): ``list_creative_formats`` and
``list_authorized_properties`` were added here to eliminate a THIRD
independent skill->task derivation that had diverged from this map on 6
entries (tests/e2e/test_a2a_protocol_compliance.py's ``adcp_skills`` was a
hand-typed set combined with ``skill.replace("_", "-")`` name derivation).
``list_creative_formats`` resolves to a real pinned task
(``list-creative-formats``); ``list_authorized_properties`` does not (see
``_KNOWN_MISSING_SCHEMA_SKILLS`` in test_a2a_protocol_compliance.py, which
already tracked it as a known gap before this map knew about it).
"""

from __future__ import annotations

SKILL_TO_ADCP_TASK: dict[str, str | None] = {
    "get_products": "get-products",
    "create_media_buy": "create-media-buy",
    "update_media_buy": "update-media-buy",
    "get_media_buy_delivery": "get-media-buy-delivery",
    "sync_creatives": "sync-creatives",
    "list_creatives": "list-creatives",
    "list_creative_formats": "list-creative-formats",
    # Skills without a corresponding AdCP task in the pinned index yet.
    "approve_creative": None,
    "add_creative_assets": None,
    "get_media_buy_status": None,
    "optimize_media_buy": None,
    "list_authorized_properties": None,
}
