"""The SQL FormatId allowlist must name exactly what ``core/format-id.json`` declares.

``validate_format_ids`` is PL/pgSQL, so it cannot read the pinned schema and its allowlist
is retyped by hand. That is precisely how it drifted: the pin declares six properties and
the function allowed five, so a product carrying ``pixel_ratio`` -- declared and optional
at the pin -- was refused by the database (salesagent-knd96).

Nothing caught it until an e2e_rest row did, and that is structural rather than luck:
``tests/conftest_db.py`` builds the integration schema with ``Base.metadata.create_all``,
so this function does not exist in the integration database at all
(salesagent-3cs7o.42). Only a migrated database runs it, and only e2e_rest writes to one.

So this test is the detector that does not need a database: it compares the list the
migration types against the list the pin declares, and fails when the spec gains a
seventh property.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import adcp
import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "a7c31e0f45b2_allow_pixel_ratio_in_format_ids.py"
)


def _pinned_format_id_properties() -> set[str]:
    """Every property ``core/format-id.json`` declares, read from the installed SDK."""
    schemas = Path(adcp.__file__).parent / "_schemas"
    bundle = str(adcp.get_adcp_spec_version()).rsplit(".", 1)[0]
    document = schemas / bundle / "core" / "format-id.json"
    assert document.is_file(), f"the pinned bundle has no {document}"
    return set(json.loads(document.read_text())["properties"])


def _sql_allowlist() -> set[str]:
    """The identifiers the migration's ``_ALLOWED`` array names."""
    source = _MIGRATION.read_text()
    match = re.search(r"_ALLOWED\s*=\s*\"ARRAY\[([^\]]*)\]\"", source)
    assert match, "the migration no longer defines _ALLOWED as a single ARRAY[...] literal"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_the_sql_allowlist_names_exactly_the_pinned_properties() -> None:
    pinned = _pinned_format_id_properties()
    allowed = _sql_allowlist()

    # A derivation that matches nothing passes vacuously, so assert the population first.
    assert len(pinned) >= 2, f"read only {sorted(pinned)} from the pinned format-id.json"
    assert len(allowed) >= 2, f"parsed only {sorted(allowed)} out of the migration"

    assert allowed == pinned, (
        "validate_format_ids' allowlist has drifted from core/format-id.json.\n"
        f"  pinned but not allowed (the database will REFUSE these): {sorted(pinned - allowed)}\n"
        f"  allowed but not pinned (the database accepts what the spec does not declare): "
        f"{sorted(allowed - pinned)}\n"
        "Add a migration rather than editing a revision that has run (salesagent-knd96)."
    )


@pytest.mark.parametrize("required", ["agent_url", "id"])
def test_the_required_pair_is_in_the_allowlist(required: str) -> None:
    """The two the pin marks required must be allowed, whatever else moves."""
    assert required in _sql_allowlist()
