"""Structural guard: `@storyboard-v3.1` scenarios must cite a binding that resolves.

A scenario tagged `@storyboard-v3.1` is claiming that an AdCP conformance storyboard
grades the behaviour it tests. That claim rotted silently: an audit at the 3.1.1 pin
found all 40 tagged scenarios carried a broken binding — 29 pinned to commit
`04f59d2d5` (an ancestor of beta.3, older than the repo's own pin), 11 with no
`@source` footer at all, 16 citing the *next* scenario's storyboard, and 21 claiming a
storyboard gated behind a protocol, specialism, or capability we do not declare.

None of that was detectable at `make quality` time, which is why it drifted for
months. This guard makes each failure mode fail loudly:

1. a tagged scenario has an `@source` footer
2. the footer's `ref` names the pinned spec version, not some older commit
3. the cited storyboard path exists at the pin
4. a phase named in `<id> phase:` form lives in the cited file
5. the cited storyboard is not gated by a protocol/specialism/capability we lack

Offline: reads `tests/fixtures/adcp_storyboards_pinned/index.json`, refreshed by the
`_refresh.py` next to it when the pin advances.

Allowlist policy is the repo standard — it may only shrink. Entries are seeded from
the audit baseline; each is removed as its scenario is re-pinned or retagged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES = REPO_ROOT / "tests" / "bdd" / "features"
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"
CAPABILITIES = REPO_ROOT / "src" / "core" / "tools" / "capabilities.py"

TAG = "@storyboard-v3.1"
TAGLINE_RE = re.compile(r"^\s*@[\w.\-]+(?:\s+@[\w.\-]+)*\s*$")
IDENT_RE = re.compile(r"@(T-[A-Za-z0-9_\-]+)")
SOURCE_RE = re.compile(r"@source\s+repo=\S+\s+ref=(?P<ref>\S+)(?:\s+\S+=\S+)*?\s+path=(?P<path>[^\s#]+)")
PHASE_REF_RE = re.compile(r"\b([a-z][a-z0-9_]{3,})\s+phase\b")

# Scenarios whose binding is known-broken at the audit baseline. MAY ONLY SHRINK.
# Every entry is a scenario the 3.1.1 audit found mis-bound; removing one means its
# @source now resolves (or it was retagged @schema-v3.1 and left this guard's scope).
KNOWN_BROKEN_BINDINGS: frozenset[str] = frozenset(
    {
        "T-UC-001-storyboard-proposal-finalize-action",
        "T-UC-001-storyboard-finalize-uses-refine-vocabulary",
        "T-UC-002-storyboard-async-submitted-envelope-task-id-roundtrip",
        "T-UC-002-storyboard-governance-approved",
        "T-UC-002-storyboard-governance-with-conditions",
        "T-UC-002-storyboard-governance-denied",
        "T-UC-002-storyboard-governance-denied-recovery",
        "T-UC-002-storyboard-inventory-list-no-match",
        "T-UC-002-storyboard-inventory-list-targeting-parity",
        "T-UC-002-storyboard-measurement-terms-rejected",
        "T-UC-002-storyboard-pending-creatives-state-transition",
        "T-UC-003-storyboard-media-buy-not-found",
        "T-UC-003-storyboard-package-not-found",
        "T-UC-003-storyboard-not-cancellable-on-recancel",
        "T-UC-003-storyboard-creative-fate-after-cancellation",
        "T-UC-004-storyboard-controller-driven-delivery-schema-compliance",
        "T-UC-004-storyboard-required-metrics-end-to-end-accountability",
        "T-UC-004-storyboard-vendor-metric-end-to-end",
        "T-UC-005-storyboard-format-id-roundtrip-from-products",
        "T-UC-005-storyboard-format-id-third-party-agent-out-of-scope",
        "T-UC-005-storyboard-baseline-format-id-object-shape",
        "T-UC-006-storyboard-provenance-required-rejection",
        "T-UC-006-storyboard-provenance-digital-source-type-missing",
        "T-UC-006-storyboard-provenance-disclosure-missing",
        "T-UC-006-storyboard-provenance-corrected-acceptance",
        "T-UC-006-storyboard-provenance-claim-contradicted",
        "T-UC-006-storyboard-multi-format-sync",
        "T-UC-006-storyboard-format-id-roundtrip-on-sync",
        "T-UC-006-storyboard-creative-reception-stateful-render",
        "T-UC-008-storyboard-baseline-end-to-end",
        "T-UC-008-storyboard-activate-agent-destination",
        "T-UC-008-storyboard-activate-platform-destination",
        "T-UC-014-storyboard-baseline-session-id-roundtrip",
        "T-UC-018-storyboard-list-all-creatives-after-sync",
        "T-UC-018-storyboard-filter-by-format-id-object",
        "T-UC-018-storyboard-filter-by-concept-id",
        "T-UC-019-storyboard-post-create-status-poll",
        "T-UC-020-storyboard-build-vast-tag-from-synced-creative",
        "T-UC-021-storyboard-preview-display-from-synced-manifest",
        "T-UC-030-storyboard-binding-used-during-create-media-buy",
    }
)


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _declared() -> tuple[set[str], set[str]]:
    text = CAPABILITIES.read_text(encoding="utf-8")
    specialisms = {s.replace("_", "-") for s in re.findall(r"AdcpSpecialism\.(\w+)", text)}
    protocols = {p.replace("_", "-") for p in re.findall(r"SupportedProtocol\.(\w+)", text)}
    return specialisms, protocols


def _index_reachable(rel_index: str, specialisms: set[str], protocols: set[str]) -> bool:
    """Can we reach the index that pulls a scenario in, given what we declare?"""
    parts = rel_index.split("/")
    if parts[0] == "specialisms":
        return parts[1] in specialisms
    if parts[0] == "protocols":
        return parts[1] in protocols
    return True


def _tagged_scenarios() -> list[tuple[str, str, str]]:
    """(identifier, feature name, comment block) for every @storyboard-v3.1 scenario."""
    found: list[tuple[str, str, str]] = []
    for feature in sorted(FEATURES.glob("*.feature")):
        lines = feature.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            if TAG not in line or not TAGLINE_RE.match(line):
                continue
            ident = next((m.group(1) for t in line.split() if (m := IDENT_RE.match(t))), "(unnamed)")
            block: list[str] = []
            for probe in range(idx, min(idx + 80, len(lines))):
                if probe > idx and TAGLINE_RE.match(lines[probe]):
                    break
                block.append(lines[probe])
            found.append((ident, feature.name, "\n".join(block)))
    return found


def _violations() -> dict[str, str]:
    """Map identifier -> first binding defect found. Empty when every binding resolves."""
    index = _index()
    version = index["adcp_spec_version"]
    storyboards: dict[str, dict] = index["storyboards"]
    specialisms, protocols = _declared()
    bad: dict[str, str] = {}

    for ident, feature, block in _tagged_scenarios():
        match = SOURCE_RE.search(block)
        if not match:
            bad[ident] = f"{feature}: no @source footer"
            continue

        ref, raw_path = match.group("ref"), match.group("path")
        if version not in ref:
            bad[ident] = f"{feature}: @source ref {ref!r} does not name the pinned version {version}"
            continue

        rel = re.sub(r"^(dist/compliance/[^/]+/|static/compliance/source/)", "", raw_path)
        if "schemas" in rel:
            continue  # schema-only citation; nothing storyboard-shaped to resolve
        entry = storyboards.get(rel)
        if entry is None:
            bad[ident] = f"{feature}: cited storyboard {rel!r} does not exist at {version}"
            continue

        # Reachability before tier: a scenario's directory does not determine its
        # gate. `governance_conditions` sits under `protocols/media-buy/scenarios/`
        # but is pulled in only by specialisms we do not declare, so a path-prefix
        # check reports it ungated.
        owners: list[str] = entry.get("required_by", [])
        if owners and not any(_index_reachable(o, specialisms, protocols) for o in owners):
            bad[ident] = f"{feature}: only required by {owners} — all behind gates we do not declare"
            continue

        if (specialism := entry.get("specialism")) and specialism not in specialisms:
            bad[ident] = f"{feature}: gated by undeclared specialism {specialism!r}"
            continue
        if (protocol := entry.get("protocol")) and protocol not in protocols:
            bad[ident] = f"{feature}: gated by undeclared protocol {protocol!r}"
            continue
        if capability := entry.get("requires_capability"):
            bad[ident] = f"{feature}: gated by requires_capability {capability['path']}"
            continue

        known = set(entry.get("phases", []))
        for named in {m.group(1) for m in PHASE_REF_RE.finditer(block)}:
            if any(named in sb.get("phases", []) for sb in storyboards.values()) and named not in known:
                bad[ident] = f"{feature}: names phase {named!r}, absent from cited {rel!r}"
                break

    return bad


def test_storyboard_bindings_resolve_at_the_pin() -> None:
    """Every @storyboard-v3.1 scenario cites a binding that resolves at the pinned version."""
    new = {k: v for k, v in _violations().items() if k not in KNOWN_BROKEN_BINDINGS}
    assert new == {}, (
        "New broken @storyboard-v3.1 bindings. A scenario carrying this tag claims an AdCP "
        "storyboard grades it — the claim must resolve at the pinned version:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(new.items()))
    )


def test_allowlist_has_no_stale_entries() -> None:
    """Allowlisted scenarios that now resolve must be removed — the ratchet only shrinks."""
    broken = set(_violations())
    identifiers = {ident for ident, _, _ in _tagged_scenarios()}
    stale = {e for e in KNOWN_BROKEN_BINDINGS if e in identifiers and e not in broken}
    assert stale == set(), "These bindings now resolve; remove them from KNOWN_BROKEN_BINDINGS:\n" + "\n".join(
        f"  {e}" for e in sorted(stale)
    )


@pytest.mark.parametrize(
    "block,expected",
    [
        ("  @T-X-storyboard-a @storyboard-v3.1\n  Scenario: x\n", "no @source footer"),
        (
            "  @T-X-storyboard-b @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1-04f59d2d5 path=protocols/media-buy/index.yaml\n",
            "does not name the pinned version",
        ),
        (
            "  @T-X-storyboard-c @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1.1 path=protocols/media-buy/scenarios/nope.yaml\n",
            "does not exist",
        ),
    ],
)
def test_guard_catches_each_failure_mode(tmp_path: Path, monkeypatch, block: str, expected: str) -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    feature = tmp_path / "BR-UC-999-meta.feature"
    feature.write_text("Feature: meta\n\n" + block, encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.FEATURES", tmp_path)
    found = _violations()
    assert found, f"guard did not flag the {expected!r} case"
    assert expected in next(iter(found.values()))
