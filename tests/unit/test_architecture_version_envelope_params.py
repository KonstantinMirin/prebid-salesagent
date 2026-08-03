"""Structural guard: MCP tool wrappers must accept the AdCP version-envelope fields.

salesagent-xg5w.1: FastMCP derives its tool-call schema from the Python function
signature, so a wrapper that doesn't declare ``adcp_version``/``adcp_major_version``
(AdcpVersionEnvelope, part of every AdCP request) rejects real conformance-runner
traffic with "Unexpected keyword argument" before the request ever reaches _impl.
Codebase-scan for xg5w.1 found this on 10 of 16 registered tools; this guard pins
the fix and prevents new tools from reintroducing the gap.
"""

import inspect

from tests.unit.test_architecture_wrapper_typed_params import MCP_WRAPPERS

# Tools whose request schema does not (yet) inherit AdcpVersionEnvelope, so there
# is nothing to thread adcp_version/adcp_major_version into. Each entry needs a
# real reason -- this allowlist shrinks as the underlying schema gaps close.
_ALLOWLIST: dict[str, str] = {
    "list_authorized_properties": "local SalesAgentBaseModel schema; type removed from AdCP spec at 3.2.0",
    "get_media_buys": "GetMediaBuysRequest is a hand-duplicated local schema, not the library type -- salesagent-xg5w.9",
}


def _accepts_version_envelope(module_path: str, func_name: str) -> tuple[bool, bool]:
    import importlib

    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)
    params = inspect.signature(func).parameters
    return "adcp_version" in params, "adcp_major_version" in params


def test_mcp_wrappers_accept_version_envelope_fields():
    """Every registered MCP tool (not allowlisted) must declare both fields."""
    violations = []
    for module_path, func_name in MCP_WRAPPERS:
        if func_name in _ALLOWLIST:
            continue
        has_version, has_major_version = _accepts_version_envelope(module_path, func_name)
        if not (has_version and has_major_version):
            violations.append(
                f"  {module_path}.{func_name} (adcp_version={has_version}, adcp_major_version={has_major_version})"
            )

    assert not violations, (
        "MCP wrappers missing adcp_version/adcp_major_version params -- FastMCP will reject real "
        "AdCP requests carrying them as 'Unexpected keyword argument' (salesagent-xg5w.1):\n" + "\n".join(violations)
    )


def test_allowlist_has_no_stale_entries():
    """Allowlist entries must still be missing the fields -- once fixed, remove them."""
    stale = []
    for func_name, _reason in _ALLOWLIST.items():
        matches = [pair for pair in MCP_WRAPPERS if pair[1] == func_name]
        assert matches, f"{func_name} is allowlisted but not in MCP_WRAPPERS -- remove the stale entry"
        module_path, _ = matches[0]
        has_version, has_major_version = _accepts_version_envelope(module_path, func_name)
        if has_version and has_major_version:
            stale.append(f"  {func_name}: now declares both fields -- remove from allowlist")
    assert not stale, "Stale version-envelope allowlist entries:\n" + "\n".join(stale)


def test_guard_catches_a_missing_wrapper():
    """Meta-test: the check must actually fail when a tool is missing the fields.

    Uses list_authorized_properties (allowlisted, so genuinely missing both fields
    today) as a stand-in for "a real regression" to prove the assertion isn't vacuous.
    """
    has_version, has_major_version = _accepts_version_envelope(
        "src.core.tools.properties", "list_authorized_properties"
    )
    assert not (has_version and has_major_version), (
        "list_authorized_properties now has both fields -- this meta-test's premise is stale, "
        "swap in a still-missing tool or drop the allowlist entry"
    )


def test_guard_passes_for_a_fixed_wrapper():
    """Meta-test: a fixed wrapper (get_products) must satisfy the positive check."""
    has_version, has_major_version = _accepts_version_envelope("src.core.tools.products", "get_products")
    assert has_version and has_major_version
