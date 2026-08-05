"""Locate the pinned spec version's schema tree inside the installed adcp SDK.

Single source of truth for "which directory holds the SDK's bundled JSON
schemas for the currently-pinned spec version" — moved here from
tests/e2e/adcp_schema_validator.py once a second (integration-level) consumer
needed it, since importing an e2e module from tests/integration/ is backwards
layering.
"""

from __future__ import annotations

from pathlib import Path


def sdk_schema_root() -> Path:
    """The installed adcp SDK's bundled schema tree for the pinned spec version.

    The SDK stores schemas under ``adcp/_schemas/<major.minor>/`` (e.g. the
    3.1.1 spec lives in ``_schemas/3.1/``; its ``index.json`` carries the full
    ``adcp_version``).
    """
    import adcp

    spec_version = adcp.get_adcp_spec_version()
    major_minor = ".".join(spec_version.split(".")[:2])
    root = Path(adcp.__file__).parent / "_schemas" / major_minor
    if not root.is_dir():
        raise AssertionError(
            f"Installed adcp SDK (spec {spec_version}) has no bundled schema tree at {root} — "
            "the SDK layout changed; update sdk_schema_root()."
        )
    return root
