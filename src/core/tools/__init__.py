"""
Raw AdCP tool functions without FastMCP decorators.

This module re-exports raw wrapper functions from individual tool modules.
Each raw function is defined in its respective tool module and simply calls
the shared _impl() function.

This eliminates the monolithic __init__.py pattern and keeps code organized
by tool domain.
"""

# Re-export raw functions from tool modules
from src.core.tools.accounts import list_accounts_raw, sync_accounts_raw
from src.core.tools.capabilities import get_adcp_capabilities_raw
from src.core.tools.creative_formats import list_creative_formats_raw
from src.core.tools.creatives import list_creatives_raw, sync_creatives_raw
from src.core.tools.media_buy_create import create_media_buy_raw
from src.core.tools.media_buy_delivery import get_media_buy_delivery_raw
from src.core.tools.media_buy_list import get_media_buys_raw
from src.core.tools.media_buy_update import update_media_buy_raw
from src.core.tools.performance import update_performance_index_raw
from src.core.tools.products import get_products_raw
from src.core.tools.properties import list_authorized_properties_raw

# get_signals is exposed on MCP/A2A/REST but is deliberately NOT declared in
# get_adcp_capabilities' supported_protocols, so it runs UNDECLARED and UNGRADED.
#
# Per the pinned spec (v3.1.1 dist/schemas/3.1.1/protocol/get-adcp-capabilities-response.json),
# supported_protocols values "both (a) declare which tools the agent implements and
# (b) commit the agent to pass the baseline compliance storyboard at
# /compliance/{version}/protocols/{protocol}/", and the response's signals section is
# "Only present if signals is in supported_protocols". Declaring "signals" would therefore
# commit us to dist/compliance/3.1.1/protocols/signals/ — which we cannot pass while
# activate_signal is intentionally unregistered.
#
# So the discovery surfaces disagree ON PURPOSE: the AgentCard advertises the tool we
# actually serve, while capabilities declines a conformance claim we cannot honor.
# Declaring the signals protocol (and emitting the signals capabilities section) is
# tracked with activate_signal in GH #1593.
from src.core.tools.signals import get_signals_raw

__all__ = [
    "get_signals_raw",
    "list_accounts_raw",
    "sync_accounts_raw",
    "get_adcp_capabilities_raw",
    "get_products_raw",
    "create_media_buy_raw",
    "sync_creatives_raw",
    "list_creatives_raw",
    "list_creative_formats_raw",
    "list_authorized_properties_raw",
    "update_media_buy_raw",
    "get_media_buy_delivery_raw",
    "get_media_buys_raw",
    "update_performance_index_raw",
]
