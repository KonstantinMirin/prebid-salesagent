"""Guard: the TS conformance runner must target the SAME AdCP version this repo pins.

The storyboard job grades us with `@adcp/sdk`'s runner. That SDK declares which
AdCP release its CLIENT is built for in its own ``package.json`` (``adcp_version``),
independently of the ``--compliance-version`` / ``--compliance-dir`` we hand it.

Those two can disagree silently, and did: `@adcp/sdk@9.3.0` declared **3.1.0**
while this repo then pinned **3.1.1**, so for its whole life the baseline was
measured by a client one release behind the storyboards it was grading against.
Nothing failed — the storyboards and schemas were the right version, only the code
driving them was not. That incident is why this guard exists.

Pointing a mismatched client at the right storyboards is exactly the kind of
"looks measured, isn't" result this whole module exists to prevent, so it gets a
guard rather than a comment.

Lives in tests/storyboard/ (not tests/unit/) because it reads the INSTALLED
package: the assertion is about what will actually run, not about what a manifest
claims. That directory is only meaningfully collected where the runner's npm deps
exist — the same precondition the conformance module itself has.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_PACKAGE_JSON = Path(__file__).parent / "runner" / "node_modules" / "@adcp" / "sdk" / "package.json"

sys.path.insert(0, str(_REPO_ROOT))

from scripts.audit import storyboard_spec  # noqa: E402


def test_runner_sdk_targets_the_pinned_adcp_version() -> None:
    """The runner's adcp_version matches the repo's pin, with no divergence to accept.

    This guard carried one accepted divergence for the life of the 14.0.0-rc line, which
    declared 3.2.0-rc.4 against a 3.2.1 pin: the rc line was the only one carrying the A2A
    request-signing dispatch (adcp-client#2967), so taking the nearest version-matched
    release meant giving up the A2A card entirely. ``@adcp/sdk@14.4.0`` is on the same line
    and declares 3.2.1 exactly, which is the retirement condition the record stated, so the
    record is gone and the assertion below stands on its own.
    """
    if not _SDK_PACKAGE_JSON.is_file():
        pytest.fail(
            f"conformance runner SDK not installed at {_SDK_PACKAGE_JSON}. "
            "Run `npm ci` in tests/storyboard/runner/ — this guard asserts on the "
            "INSTALLED package deliberately, so a missing install is a real failure "
            "and not something to skip past."
        )

    sdk = json.loads(_SDK_PACKAGE_JSON.read_text(encoding="utf-8"))
    sdk_targets = sdk.get("adcp_version")
    repo_pins = storyboard_spec.pinned_version(_REPO_ROOT)

    assert sdk_targets == repo_pins, (
        f"conformance runner targets AdCP {sdk_targets!r} but this repo pins {repo_pins!r}.\n"
        f"  installed: @adcp/sdk@{sdk.get('version')}\n"
        "Grading with a client built for a different release measures the wrong contract, "
        "however right the --compliance-version happens to be. Something moved: a runner "
        "upgrade, a pin bump, or a backport landing. Either pin an @adcp/sdk whose "
        "adcp_version matches (check `npm view @adcp/sdk@<v> adcp_version`) or move the "
        "repo's pin deliberately per docs/adcp-spec-version.md. A divergence this repo "
        "chooses to accept is a deliberate decision with a reason recorded here -- the last "
        "one was the 14.0.0-rc line, retired when 14.4.0 declared the pin exactly."
    )
