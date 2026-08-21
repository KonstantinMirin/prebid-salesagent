"""CI guard: assert the adcp SDK pin targets the expected AdCP spec version."""

import adcp

from tests.helpers.adcp_pin import EXPECTED_SPEC_VERSION


def test_adcp_spec_version_matches_pin() -> None:
    """Verify SDK pin targets the spec version this codebase expects.

    Failure here means the adcp Python SDK pin in pyproject.toml has shifted
    to a version that targets a different AdCP spec version. Either revert
    the pin or follow docs/adcp-spec-version.md to update
    EXPECTED_SPEC_VERSION and the related references it lists.
    """
    actual = adcp.get_adcp_spec_version()
    assert actual == EXPECTED_SPEC_VERSION, (
        f"adcp SDK targets spec {actual}, but this codebase expects "
        f"{EXPECTED_SPEC_VERSION}. See docs/adcp-spec-version.md for "
        f"reconciliation steps."
    )


def test_the_vendored_schema_tree_matches_the_pin() -> None:
    """The vendored schema fixtures must be the version the SDK pin targets.

    ``tests/fixtures/adcp_schemas_pinned/<version>/`` carries the schema documents the
    trust-root tests validate against, and the version is a DIRECTORY NAME — a literal.
    The guard above pins the SDK against ``EXPECTED_SPEC_VERSION``; nothing pinned the
    neighbouring schema tree, so a bump could move the SDK and the served ``$schema``
    while the documents were still graded against the previous version's fixtures.

    That is the same mechanism the vector guard already applies, applied to the tree
    beside it (#1757). It fails LOUDLY at bump time — which is the point: the bump
    procedure in ``docs/adcp-spec-version.md`` then has something to tell you to do.
    """
    from pathlib import Path

    tree = Path(__file__).resolve().parents[1] / "fixtures" / "adcp_schemas_pinned"
    versions = {child.name for child in tree.iterdir() if child.is_dir() and child.name[0].isdigit()}

    assert versions == {EXPECTED_SPEC_VERSION}, (
        f"the vendored schema tree carries {sorted(versions)} but the codebase is pinned to "
        f"{EXPECTED_SPEC_VERSION}. Re-vendor the fixtures for the pinned version (see "
        f"tests/fixtures/adcp_schemas_pinned/_refresh.py) and update the references "
        f"docs/adcp-spec-version.md lists — a stale tree grades our documents against the "
        f"wrong spec while every version literal in production has already moved."
    )
