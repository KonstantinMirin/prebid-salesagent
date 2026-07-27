"""Guard: a settable sync_accounts field must be applied by BOTH entry handlers.

``sync_accounts`` has two entry arms and the request schema gives them the IDENTICAL
settable field set (verified: ``Accounts`` and ``Accounts1`` in
``adcp.types.generated_poc.account.sync_accounts_request`` have the same
``model_fields``):

- provisioning        -> ``_account_fields_changed``
- settings-update     -> ``_process_settings_update_entry``

A field wired into one arm and not the other is silently accepted on the wire and
silently dropped -- the quiet-failure class CLAUDE.md bans. The
``salesagent-ck9v`` disease scan found four live instances of exactly that, so this
is a real pattern, not a hypothetical.

The known-asymmetric fields are allowlisted below, each pointing at the ticket
that will decide them. **This allowlist may only shrink.** It exists so
``notification_configs`` cannot become the next instance, not to bless the existing ones.
"""

import ast
from pathlib import Path

from tests.unit._architecture_helpers import assert_violations_match_allowlist

_ACCOUNTS_SRC = Path("src/core/tools/accounts.py")

_PROVISIONING_HANDLER = "_account_fields_changed"
_SETTINGS_UPDATE_HANDLER = "_process_settings_update_entry"

# Fields the two arms handle differently today. Each MUST cite the ticket that
# decides whether the asymmetry is correct (some probably are -- `sandbox` is part
# of the account natural key, so mutating it would re-key the account).
# salesagent-gcze carries the per-field analysis. NEVER add a row here to make a
# new field pass; wire the field into both arms instead.
#
# NOTE: `governance_agents` is deliberately NOT here. This guard's staleness check
# proved it is not a settable request field at all — neither `Accounts` nor
# `Accounts1` declares it, so `_account_fields_changed`'s
# `getattr(entry, "governance_agents", None)` always reads None and the comparison
# is dead code. That is a separate finding, recorded on salesagent-gcze; it is not
# a handler asymmetry.
_KNOWN_ASYMMETRIC: dict[str, str] = {
    "billing": "salesagent-gcze — may be immutable after provisioning; undecided",
    "sandbox": "salesagent-gcze — part of the natural key; mutating would re-key the account",
}

# Settable fields NEITHER arm applies: accepted on the wire, then silently dropped.
# A different defect from asymmetry (both arms agree — they agree on ignoring the
# buyer), so it gets its own pin rather than being folded into the set above, which
# would let a field move between the two debts unnoticed.
# Same rule: may only shrink; never add a row to make a new field pass.
_KNOWN_DROPPED_BY_BOTH: dict[str, str] = {
    "billing_entity": "salesagent-gcze — accepted on the wire, no DB column, never applied",
    "preferred_reporting_protocol": "salesagent-gcze — same as billing_entity",
}


def _settable_request_fields() -> set[str]:
    """The settable fields BOTH request arms declare (excluding the routing keys)."""
    from adcp.types.generated_poc.account.sync_accounts_request import Accounts, Accounts1

    common = set(Accounts.model_fields) & set(Accounts1.model_fields)
    # `account` selects the arm; brand/operator are the natural key, not settings.
    return common - {"account", "brand", "operator"}


def _fields_applied_in(function_name: str) -> set[str]:
    """Fields *function_name* writes into its ``changes`` dict.

    APPLIED, not merely mentioned. Both handlers ECHO fields they never apply --
    ``_process_settings_update_entry`` reads ``existing.billing`` to build the
    response while never letting the buyer change it -- so a reader that counted
    any mention would call that symmetric and the guard would be worthless.
    The precise signal is ``changes["<field>"] = ...``, which is exactly "this arm
    lets the buyer set this field".
    """
    tree = ast.parse(_ACCOUNTS_SRC.read_text())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == function_name):
            continue
        applied: set[str] = set()
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            for target in sub.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "changes"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    applied.add(target.slice.value)
        return applied
    raise AssertionError(f"{function_name} not found in {_ACCOUNTS_SRC}")


def _asymmetric_fields_found() -> set[tuple[str]]:
    """Settable fields applied by exactly ONE of the two arms."""
    provisioning = _fields_applied_in(_PROVISIONING_HANDLER)
    settings_update = _fields_applied_in(_SETTINGS_UPDATE_HANDLER)
    return {(field,) for field in _settable_request_fields() if (field in provisioning) != (field in settings_update)}


def test_settable_fields_are_applied_by_both_entry_handlers():
    """Every settable field is applied by both arms, or is a recorded asymmetry.

    One assertion covers BOTH directions via the canonical helper: a new
    asymmetry fails as a "new violation", and an allowlisted field that became
    symmetric (or stopped being settable) fails as a "stale entry" — so the
    allowlist cannot silently outlive the debt it excuses.
    """
    assert_violations_match_allowlist(
        _asymmetric_fields_found(),
        {(field,) for field in _KNOWN_ASYMMETRIC},
        fix_hint=(
            "sync_accounts gives BOTH entry arms the same settable field set. Wire the "
            "field into _account_fields_changed AND _process_settings_update_entry. Only "
            "record an asymmetry in _KNOWN_ASYMMETRIC with a ticket that will decide it."
        ),
    )


def _dropped_by_both_found() -> set[tuple[str]]:
    """Settable fields NEITHER arm applies — accepted, then silently discarded."""
    applied = _fields_applied_in(_PROVISIONING_HANDLER) | _fields_applied_in(_SETTINGS_UPDATE_HANDLER)
    return {(field,) for field in _settable_request_fields() - applied}


def test_no_settable_field_is_silently_dropped_by_both_handlers():
    """A field the buyer may set must reach persistence, or be rejected explicitly.

    Accepting a field on the wire and discarding it is the quiet-failure pattern
    CLAUDE.md bans: the buyer gets a success response for a change that never
    happened.
    """
    assert_violations_match_allowlist(
        _dropped_by_both_found(),
        {(field,) for field in _KNOWN_DROPPED_BY_BOTH},
        fix_hint=(
            "Either apply the field in both entry handlers, or reject it explicitly "
            "with UNSUPPORTED_FEATURE. Silently accepting and dropping it is not an option."
        ),
    )


class TestMatcherModelsTheForm:
    """Self-tests: the reader finds real names and the guard can actually fail."""

    def test_notification_configs_is_settable_and_not_allowlisted(self):
        """The field this guard was built to protect is genuinely in scope."""
        assert "notification_configs" in _settable_request_fields()
        assert "notification_configs" not in _KNOWN_ASYMMETRIC

    def test_notification_configs_reaches_both_arms(self):
        assert "notification_configs" in _fields_applied_in(_PROVISIONING_HANDLER)
        assert "notification_configs" in _fields_applied_in(_SETTINGS_UPDATE_HANDLER)

    def test_payment_terms_reaches_both_arms(self):
        # The one field that was already symmetric before this work.
        assert "payment_terms" in _fields_applied_in(_PROVISIONING_HANDLER)
        assert "payment_terms" in _fields_applied_in(_SETTINGS_UPDATE_HANDLER)

    def test_a_known_asymmetry_really_is_asymmetric(self):
        """Proves the guard would FIRE without the allowlist -- not vacuously green."""
        assert "billing" in _fields_applied_in(_PROVISIONING_HANDLER)
        assert "billing" not in _fields_applied_in(_SETTINGS_UPDATE_HANDLER)

    def test_governance_agents_is_not_a_settable_request_field(self):
        """`_account_fields_changed` compares a field the request cannot carry.

        Pins the finding rather than leaving it as a comment: if a future SDK adds
        `governance_agents` to the request arms, this fails and the dead comparison
        becomes live code that must then be wired into BOTH arms.
        """
        assert "governance_agents" not in _settable_request_fields()

    def test_readers_are_not_trivially_empty(self):
        assert len(_settable_request_fields()) >= 5
        assert len(_fields_applied_in(_PROVISIONING_HANDLER)) >= 3
