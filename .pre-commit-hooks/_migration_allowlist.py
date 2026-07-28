"""Single source of truth for the migration-completeness allowlists.

Two things enforce the "every migration has a non-empty upgrade() and downgrade()" rule: the
pre-push hook ``check_migration_completeness.py`` and the pytest guard
``tests/unit/test_architecture_migration_completeness.py``. They had drifted — the guard carried an
allowlist and the hook carried none — so the hook was RED on an unchanged tree while ``make
quality`` and CI were green. Nothing surfaced that, because no CI job runs the pre-push stage at all
(salesagent-5v2w); it showed up only when someone pushed a range touching a migration.

Keeping the lists here means the two enforcers cannot disagree again. Both import from this module.
Allowlists shrink as violations are fixed.

FIXME(#1566): these legacy migrations have incomplete downgrades.
"""

from __future__ import annotations

# Migrations whose downgrade() is intentionally empty.
KNOWN_EMPTY_DOWNGRADE: frozenset[str] = frozenset(
    {
        # Legacy: data migration (adds default values), no structural revert needed.
        # Its own docstring: the migration is about making things idempotent, and the revert is
        # handled by downgrading migration 014.
        "017_handle_partial_schemas.py",
        # Legacy: fixes JSON encoding, no structural revert
        "e81e275c9b29_fix_price_guidance_json_encoding.py",
    }
)
