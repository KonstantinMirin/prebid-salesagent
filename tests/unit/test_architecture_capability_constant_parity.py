"""Guard: an advertised capability value must be DERIVED from its enforced constant.

Regression guard for the idempotency replay-TTL drift: ``get_adcp_capabilities``
once advertised ``replay_ttl_seconds=86400`` as a bare literal while the *enforced*
TTL lived in ``DEFAULT_REPLAY_TTL``. A literal and a constant are two sources for one
value and drift independently — the buyer is then told a window the server does not
enforce. Every ``replay_ttl_seconds=`` site MUST reference the constant
(``int(DEFAULT_REPLAY_TTL.total_seconds())``), never a hardcoded number.

This is the AST-detectable slice of semantic single-source-of-truth. A value-counting
"duplicate literal" guard is deliberately NOT used: 86400 ("seconds per day") and 3600
("seconds per hour") have many legitimate unrelated uses in src/, so counting literals
would be almost all false positives. Keying on the capability KEYWORD instead is exact.
The non-AST-detectable slice (one invariant computed two ways) stays a review concern.
"""

import ast
from pathlib import Path

from tests.unit._architecture_helpers import iter_call_expressions

# Capability keywords whose value must be derived from an enforced constant, not a literal.
_DERIVED_CAPABILITY_KEYWORDS = {"replay_ttl_seconds"}

# Builders whose output must stay DERIVED FROM ITS ENFORCED SOURCE and must never
# become tenant-declarable (#1592 T1a). ``account.sandbox`` comes from the
# ``account_sandbox`` column and ``account.supported_billing`` from
# ``resolve_supported_billing`` -- the same function the sync_accounts billing gate
# calls, so the advertised policy and the enforced policy cannot diverge. The
# ``adcp.*`` block derives from SUPPORTED_ADCP_MAJORS/VERSIONS plus
# ``get_idempotency_posture``.
#
# The capability declaration store is explicitly NOT allowed to override these: a
# tenant that could declare `supported_billing` would advertise a billing policy
# sync_accounts then refuses to honour. This is a structural check, not a
# data-driven one, precisely because a future migration would pick a store key no
# fixture could predict -- and because CapabilityDeclarations' extra="forbid"
# rejects an unknown key at parse time, so a "declare an override and assert it is
# ignored" test would never reach its assertion.
_DERIVATION_ONLY_BUILDERS = ("_build_account_block", "_build_adcp_block")
_DECLARATION_STORE_NAMES = ("capability_declarations", "CapabilityDeclarations")


def _literal_capability_sites_in(source: str) -> list[str]:
    """Return ``keyword@line`` for capability keywords assigned a bare numeric literal."""
    tree = ast.parse(source)
    out: list[str] = []
    for node in iter_call_expressions(tree):
        for kw in node.keywords:
            if (
                kw.arg in _DERIVED_CAPABILITY_KEYWORDS
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, (int, float))
                and not isinstance(kw.value.value, bool)
            ):
                out.append(f"{kw.arg}@{kw.value.lineno}")
    return out


def test_capability_values_are_derived_not_literal():
    """No advertised capability keyword may be a hardcoded number anywhere in src/.

    Core invariant: one source of truth for the replay window — the enforced
    constant. A literal in the capability response drifts from enforcement
    silently (the #1b bug class).
    """
    offenders: list[str] = []
    for path in Path("src").rglob("*.py"):
        try:
            for site in _literal_capability_sites_in(path.read_text()):
                offenders.append(f"{path}:{site.split('@')[1]} ({site.split('@')[0]})")
        except SyntaxError:
            continue
    assert not offenders, (
        "Advertised capability values must derive from their enforced constant "
        "(e.g. replay_ttl_seconds=int(DEFAULT_REPLAY_TTL.total_seconds())), not a "
        f"bare literal, at: {offenders}"
    )


def _declaration_reads_in_builders(source: str) -> list[str]:
    """Return ``builder@line`` for any read of the declaration store inside a
    derivation-only builder."""
    tree = ast.parse(source)
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in _DERIVATION_ONLY_BUILDERS):
            continue
        for sub in ast.walk(node):
            name = None
            if isinstance(sub, ast.Name):
                name = sub.id
            elif isinstance(sub, ast.Attribute):
                name = sub.attr
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                name = sub.value
            if name in _DECLARATION_STORE_NAMES:
                out.append(f"{node.name}@{sub.lineno}")
    return out


def test_account_and_adcp_blocks_are_not_declaration_driven():
    """``account.*`` and ``adcp.*`` must stay derived, never store-driven.

    Core invariant: the capabilities response may only advertise what some other
    part of the system ENFORCES. `supported_billing` is shared with the
    sync_accounts gate; `sandbox` is the provisioning gate's own column. Letting a
    tenant declare either would let config advertise a policy production refuses to
    honour -- the exact honesty inversion #1592 T1a exists to prevent.
    """
    offenders: list[str] = []
    for path in Path("src").rglob("*.py"):
        try:
            for site in _declaration_reads_in_builders(path.read_text()):
                builder, line = site.split("@")
                offenders.append(f"{path}:{line} ({builder})")
        except SyntaxError:
            continue
    assert not offenders, (
        "account.*/adcp.* must derive from their enforced sources, never from the "
        f"capability declaration store, at: {offenders}"
    )


class TestDerivationOnlyMatcherModelsTheForm:
    """Self-tests for the derivation-only matcher."""

    def test_declaration_read_in_builder_is_flagged(self):
        src = "def _build_account_block(tenant):\n    return tenant.get('capability_declarations')\n"
        assert _declaration_reads_in_builders(src)

    def test_declaration_read_outside_those_builders_is_ignored(self):
        src = "def _get_adcp_capabilities_impl(tenant):\n    return tenant.get('capability_declarations')\n"
        assert not _declaration_reads_in_builders(src)

    def test_attribute_access_form_is_also_flagged(self):
        # A future refactor to TenantContext attribute access must not slip past
        # a string-literal-only matcher.
        src = "def _build_adcp_block(tenant):\n    return tenant.capability_declarations\n"
        assert _declaration_reads_in_builders(src)

    def test_derived_builder_passes(self):
        src = "def _build_account_block(tenant):\n    return tenant.get('account_sandbox', True)\n"
        assert not _declaration_reads_in_builders(src)


class TestMatcherModelsTheForm:
    """Self-tests: the matcher flags a literal and passes a derived expression."""

    def test_bare_literal_is_flagged(self):
        assert _literal_capability_sites_in("Idempotency(supported=True, replay_ttl_seconds=86400)")

    def test_derived_expression_passes(self):
        src = "Idempotency(supported=True, replay_ttl_seconds=int(DEFAULT_REPLAY_TTL.total_seconds()))"
        assert not _literal_capability_sites_in(src)

    def test_unrelated_literal_keyword_ignored(self):
        # A bare number on an UNREGISTERED keyword is not this guard's concern.
        assert not _literal_capability_sites_in("Foo(timeout_seconds=86400)")
