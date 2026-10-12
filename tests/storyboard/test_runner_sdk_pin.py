"""Guard: the TS conformance runner must target the SAME AdCP version this repo pins.

The storyboard job grades us with `@adcp/sdk`'s runner. That SDK declares which
AdCP release its CLIENT is built for in its own ``package.json`` (``adcp_version``),
independently of the ``--compliance-version`` / ``--compliance-dir`` we hand it.

Those two can disagree silently, and did: `@adcp/sdk@9.3.0` declares **3.1.0**
while this repo pins **3.1.1**, so for its whole life the baseline was measured by
a client one release behind the storyboards it was grading against. Nothing failed
— the storyboards and schemas were the right version, only the code driving them
was not. `@adcp/sdk@11.0.0` is the newest release still on 3.1.1 (11.1.0 moves to
3.1.2).

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

#: RETIRED. There is no accepted divergence any more: the runner declares this repo's pin
#: exactly, so the assertion below is the whole check and `None` can never equal an observed
#: triple.
#:
#: THE RETIREMENT CONDITION WAS WRITTEN HERE AND IS NOW MET. The previous record ended
#: "retire the pin when a line both declares this repo's pin and carries the A2A signing
#: dispatch". ``@adcp/sdk@14.4.0`` does both:
#:
#:   * it declares ``adcp_version: 3.2.1``, which is this repo's pin (verified:
#:     ``npm view @adcp/sdk@14.4.0 adcp_version`` -> ``3.2.1``);
#:   * it is on the 14 line, so it carries the A2A request-signing dispatch
#:     (adcp-client#2967, merged 2026-09-20) that 14.0.0-rc.42 was pinned for. Without that
#:     dispatch every ``signed_requests`` vector on the A2A card is ungradable, which is why
#:     the 14 line was never a free choice. 14.4.0 > 14.0.0-rc.42, so the dispatch is in.
#:
#: WHAT THE OLD RECORD GOT WRONG BY STANDING TOO LONG, worth keeping because the mistake was
#: not in its reasoning: it said "3.1.1 is the contract this seller implements", which was
#: true when written and false by the time it fired. salesagent-8qela moved the repo to
#: 3.2.1, and the record's third element still named 3.1.1 -- so the guard was comparing the
#: installed runner against a pin the repo had left behind, and its failure message read as
#: though the runner had moved. Nothing had: the repo had. The same staleness disease as the
#: pyproject pin comment (salesagent-8qela.165) and the stranded allowlist row (.163): one
#: change, correct, with its surrounding record left describing the old world.
#:
#: The epic that moved the pin SAID this: "Conformance runner: @adcp/sdk@14.4.0, which
#: declares 3.2.1 exactly, so the accepted-divergence record is retired." That was recorded
#: before the storyboard leg was ever run against the new pin, and it was re-derived from npm
#: afterwards at the cost of a wrong intermediate conclusion (salesagent-8qela.160). Read the
#: record before measuring.
#:
#: IF A DIVERGENCE EVER RETURNS, restore a triple here rather than widening the assertion --
#: keyed ``(sdk version, sdk adcp_version, repo pin)`` so a move on ANY of the three fails and
#: asks for a decision instead of widening quietly. That design was right and is why this
#: fired at all.
_ACCEPTED_DIVERGENCE: tuple[str, str, str] | None = None


def test_runner_sdk_targets_the_pinned_adcp_version() -> None:
    """The runner's adcp_version matches the repo's pin, or is the one accepted divergence.

    Not an xfail. An xfail would pass whatever the two versions said, including a second,
    unexamined divergence appearing beside this one. Pinning the triple keeps the assertion
    real: the known state passes, and any movement -- a runner upgrade, a backport landing, a
    deliberate pin bump -- fails and asks for a decision.
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

    observed = (sdk.get("version"), sdk_targets, repo_pins)
    if observed == _ACCEPTED_DIVERGENCE:
        return

    assert sdk_targets == repo_pins, (
        f"conformance runner targets AdCP {sdk_targets!r} but this repo pins {repo_pins!r}.\n"
        f"  installed: @adcp/sdk@{sdk.get('version')}\n"
        f"  accepted divergence: {_ACCEPTED_DIVERGENCE}\n"
        "Grading with a client built for a different release measures the wrong contract, "
        "however right the --compliance-version happens to be. This triple is not the accepted "
        "one, so something moved: a runner upgrade, a pin bump, or a backport landing. Either "
        "pin an @adcp/sdk whose adcp_version matches (check `npm view @adcp/sdk@<v> "
        "adcp_version`), move the repo's pin deliberately per docs/adcp-spec-version.md, or "
        "update _ACCEPTED_DIVERGENCE above with the reason the new pair is acceptable."
    )
