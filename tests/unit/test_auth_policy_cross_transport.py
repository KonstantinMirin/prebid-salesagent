"""Cross-transport parity: MCP, A2A, and REST must agree on which skills are auth-optional.

PR #1838 review (layering lens): the "which skill/tool names are callable
without auth" concept was hand-encoded three times (MCP's AUTH_OPTIONAL_TOOLS,
A2A's DISCOVERY_SKILLS, REST's per-route resolve_auth/require_auth Depends)
with no shared source, and had drifted — list_accounts was marked
auth-optional in MCP/A2A but REST correctly required auth (matching the
graded BR-UC-011 BDD scenario and _list_accounts_impl's own enforcement).

MCP and A2A now both import src.core.auth.AUTH_OPTIONAL_SKILLS directly (so
they can't diverge from EACH OTHER); this test additionally proves REST's
independently-expressed per-route policy (a Depends default, not a set
membership) agrees with that same shared source.
"""

from __future__ import annotations

import inspect

from src.a2a_server.adcp_a2a_server import DISCOVERY_SKILLS
from src.core.auth import AUTH_OPTIONAL_SKILLS
from src.core.auth_context import require_auth, resolve_auth
from src.core.mcp_auth_middleware import AUTH_OPTIONAL_TOOLS
from src.routes import api_v1

# skill/tool name -> REST route function name (differs only for
# get_adcp_capabilities, whose REST route is named get_capabilities).
SKILL_TO_REST_ROUTE_FUNC = {
    "get_adcp_capabilities": "get_capabilities",
    "get_products": "get_products",
    "list_creative_formats": "list_creative_formats",
    "list_authorized_properties": "list_authorized_properties",
    "list_accounts": "list_accounts",
}


def _rest_requires_auth(skill_name: str) -> bool:
    """True if the REST route for *skill_name* binds identity via require_auth (not resolve_auth)."""
    func = getattr(api_v1, SKILL_TO_REST_ROUTE_FUNC[skill_name])
    sig = inspect.signature(func)
    default = sig.parameters["identity"].default
    if default is resolve_auth:
        return False
    if default is require_auth:
        return True
    raise AssertionError(f"REST route for {skill_name!r} binds identity via neither resolve_auth nor require_auth")


def test_mcp_and_a2a_share_the_same_auth_optional_set():
    assert AUTH_OPTIONAL_TOOLS is AUTH_OPTIONAL_SKILLS
    assert DISCOVERY_SKILLS is AUTH_OPTIONAL_SKILLS


def test_rest_agrees_with_the_shared_auth_optional_set():
    mismatched = []
    for skill_name in SKILL_TO_REST_ROUTE_FUNC:
        rest_requires_auth = _rest_requires_auth(skill_name)
        shared_says_optional = skill_name in AUTH_OPTIONAL_SKILLS
        if rest_requires_auth == shared_says_optional:
            mismatched.append(
                f"{skill_name}: REST requires_auth={rest_requires_auth}, "
                f"shared AUTH_OPTIONAL_SKILLS says optional={shared_says_optional}"
            )
    assert not mismatched, f"REST disagrees with MCP/A2A's auth policy: {mismatched}"


def test_list_accounts_requires_auth_on_every_transport():
    """The specific regression this bug fixed: list_accounts must NOT be auth-optional anywhere."""
    assert "list_accounts" not in AUTH_OPTIONAL_TOOLS
    assert "list_accounts" not in DISCOVERY_SKILLS
    assert _rest_requires_auth("list_accounts") is True
