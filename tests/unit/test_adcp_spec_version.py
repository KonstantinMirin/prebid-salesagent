"""CI guard: assert the adcp SDK pin targets the expected AdCP spec version."""

import re
import tomllib
from pathlib import Path

import adcp

EXPECTED_SPEC_VERSION = "3.1.1"

_REPO = Path(__file__).resolve().parents[2]

# CLAUDE.md's "AdCP Spec Version" section states both the spec version and the SDK
# pin in one sentence. Capture both so a bump that misses this file is caught.
_CLAUDE_MD_TARGETS = re.compile(
    r"This project targets AdCP spec \*\*(?P<spec>[^*]+)\*\* "
    r"via the `adcp==(?P<sdk>[^`]+)` Python SDK\."
)


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


def _pyproject_adcp_pin() -> str:
    """Return the exact `adcp==` version pinned in pyproject.toml."""
    with (_REPO / "pyproject.toml").open("rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    pins = [d.split("==", 1)[1].strip() for d in deps if d.replace(" ", "").startswith("adcp==")]
    assert len(pins) == 1, f"expected exactly one exact adcp pin in pyproject.toml, found {pins}"
    return pins[0]


def test_claude_md_states_the_pinned_versions() -> None:
    """Verify CLAUDE.md's stated spec version and SDK pin match reality.

    CLAUDE.md is what every session reads first, so a stale version line there
    silently misdirects work for the whole epic that follows it. This pins the
    prose to the two authorities it paraphrases: EXPECTED_SPEC_VERSION above
    (itself tied to the installed SDK by the test above) and the `adcp==` pin
    in pyproject.toml. Bumping the SDK means updating CLAUDE.md in the same
    change -- see docs/adcp-spec-version.md.
    """
    claude_md = (_REPO / "CLAUDE.md").read_text(encoding="utf-8")
    match = _CLAUDE_MD_TARGETS.search(claude_md)
    assert match is not None, (
        "CLAUDE.md no longer contains the 'This project targets AdCP spec "
        "**<spec>** via the `adcp==<sdk>` Python SDK.' sentence this guard "
        "pins. Restore the sentence or update _CLAUDE_MD_TARGETS."
    )

    assert match.group("spec") == EXPECTED_SPEC_VERSION, (
        f"CLAUDE.md states AdCP spec {match.group('spec')}, but this codebase "
        f"targets {EXPECTED_SPEC_VERSION}. Update CLAUDE.md."
    )

    expected_sdk = _pyproject_adcp_pin()
    assert match.group("sdk") == expected_sdk, (
        f"CLAUDE.md states adcp=={match.group('sdk')}, but pyproject.toml pins adcp=={expected_sdk}. Update CLAUDE.md."
    )
