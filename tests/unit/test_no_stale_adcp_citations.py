"""Guard: no stale AdCP citations — pre-GA markers, a dangling prose root, a wrong pin.

Three diseases, one scanner. Each is "a citation that looks authoritative and
is not", and each regressed by hand before a guard existed.

Stale pre-GA markers (#1417)
----------------------------
AdCP 3.1.0 and 3.1.1 are published as GA compliance dirs. Comments that still
cite the pre-GA ``3.1.0-rc.12`` storyboard as "latest published compliance", or
assert "no GA 3.1.0 dir exists yet", are now factually wrong and mislead the
next reader about which spec artifact grades the pinned behavior.

This regressed once (#1417 re-review): a citation-refresh commit enumerated 8
sites but touched 7, leaving stale ``rc.12`` / "no GA 3.1.0" citations in
tests/bdd/features/BR-UC-002-media-buy-status-dual-emit.feature. "Done" was a
subjective "refreshed the citations" instead of a grep that must return empty.

This test makes that grep permanent: any ``rc.12`` or "no GA 3.1.0" marker in
tests/, docs/, or src/ fails the build so a stale citation cannot reappear.

The dangling prose root (#1757)
-------------------------------
Spec prose is read from the repository-root ``docs/`` tree at the pinned tag.
The built ``dist/docs/`` tree stops at ``3.1.0``, so a citation naming
``dist/docs/3.1.1/`` resolves at NO tag — it is not stale, it is unresolvable,
and ``git cat-file -e`` on it exits non-zero. Five such citations sat in
tests/bdd/features/BR-UC-010-discover-seller-capabilities.feature and were
corrected by hand.

That file is GENERATED, which is what makes a guard load-bearing rather than
tidy: a regeneration run reinstates whatever the generator emits, and the
generator is not in this repository (searched: docs/test-obligations/, its
bdd-traceability.yaml, scripts/, src/, tests/, and the surface skill and
formula — nothing writes these ``@source`` headers). Until it is found and the
correction mirrored into it, this guard is what turns a silent regression into
a red test.

Why the marker is narrow, and must stay narrow
----------------------------------------------
Only the ``3.1.1`` root dangles. ``dist/docs/3.1.0``, and the ``-rc`` and
``-beta`` roots, all RESOLVE at ``v3.1.1`` and are legitimate citations — a
marker on ``dist/docs`` broadly would redden working ones, and a marker on
``dist/`` would redden 323 lines, since ``dist/schemas/3.1.1`` and
``dist/compliance/3.1.1`` both keep version-numbered roots.

The marker also has to tell a CITATION from a WARNING. Two files inside the
scan roots name the dangling root precisely in order to refuse it —
docs/adcp-spec-version.md and src/core/signing/verifier.py (the spec-grounding
header of the in-boundary verifier) — and reddening those would delete the
warning to satisfy the guard. The discriminator is what FOLLOWS the root: a
citation continues into a path (``dist/docs/3.1.1/building/...``), while a
warning stops at the trailing slash and closes its quoting (``there is no
``dist/docs/3.1.1/`` at that tag``). Requiring a path character after the
slash separates them with no allowlist at all, which matters because an
allowlist may only shrink and this one would need entries for prose that is
doing the right thing.

The restated pin (#1567)
------------------------
Third marker, same disease one level up: a file that states IN THE PRESENT
TENSE which AdCP spec version / ``adcp`` SDK release this project targets. This
marker used to grade such a statement against the real pin, and passed as long
as the copies agreed. **It now refuses the copy itself.**

The pin has exactly two homes. The ``adcp==`` entry in ``pyproject.toml`` is the
SDK version; ``adcp.get_adcp_spec_version()`` — reached through
``scripts.audit.storyboard_spec.pinned_version`` — is the spec version, read off
the wheel the code actually runs against. Exactly ONE document is allowed to
spell the spec version in prose, :data:`_SPEC_CLAIM_OWNER`, because documenting
the pin is that document's job; its sentence is graded by ``pinned_version()``,
which RAISES when it disagrees with the installed wheel. No document at all
restates the SDK version, because nothing can grade such a copy cheaply: the pin
can carry a PEP 440 local segment (a fork wheel pins ``adcp==9.0.0b1+prs1435.1415``),
a local segment is by definition not part of the public version, and so
``adcp==9.0.0b1`` in prose is a TRUE statement that a raw comparison calls stale.

Keeping the copies and grading them was tried and measured. It cost four unit
failures in one night in which the prose was right and the guard was comparing
wrongly; a normalization layer on one side of the comparison (and a paragraph
explaining why only one side); two agents misreading the pin out of a CLAUDE.md
quoted from a different worktree; and a guard whose own regex has a one-word
hole (``via the adcp==`` requires the article, so ``via adcp==X`` is exempt in
both directions — #2349). Refusing the copy removes the comparison, and with it
every way the comparison can be wrong. The hole survives the inversion, because
it is in the pattern rather than in the verdict, and #2349 still owns it.

The marker is deliberately the PIN CLAIM, not the digits. A bare version
matcher would fail on dated review records (docs/releases/2.0.0.md's "Spec
target — adcp==5.7.0" release note), on past-tense history (adr-001's "The
original setup used adcp==3.2.0"), and on era references ("the 3.1.0-beta.3
era"), all of which are legitimately historical and must stay green. Only a
sentence that asserts what this project targets *now* is refused, and no version
is ever spelled in this file.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from scripts.audit.storyboard_spec import pinned_version
from tests.unit._architecture_helpers import REPO_ROOT, iter_git_tracked_files

# The two disease markers from #1417 (mirrors the task's acceptance grep
# `rc\.12|no GA 3\.1\.0`). Kept as separate strings so this guard file itself
# does not textually contain the joined pattern it scans for.
_STALE_MARKERS = re.compile(r"rc\.12|no GA 3\.1\.0")

# The dangling prose root (#1757). The trailing character class is the whole
# point: it requires the root to continue into a PATH, so a line that names the
# root to warn against it (next char is a quote or a space) does not match.
_DANGLING_PROSE_ROOT = re.compile(r"dist/docs/3\.1\.1/[A-Za-z0-9_-]")

_SCAN_ROOTS = ("tests", "docs", "src")
# Text extensions worth scanning; skips binaries/fixtures where a coincidental
# byte match is meaningless.
_TEXT_SUFFIXES = {".py", ".feature", ".md", ".yaml", ".yml", ".txt", ".rst"}

_THIS_FILE = Path(__file__).resolve()


def _scanned_files():
    for path in iter_git_tracked_files(REPO_ROOT):
        if path.resolve() == _THIS_FILE:
            continue  # this guard names the markers on purpose
        if path.suffix not in _TEXT_SUFFIXES:
            continue
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in _SCAN_ROOTS:
            yield path, rel


def _offending_lines(marker: re.Pattern[str]) -> list[str]:
    """Every scanned line matching *marker*, as ``path:lineno: text``.

    One implementation for both markers. A second copy that walked the files
    again is how the two diseases end up scanned by rules that quietly differ
    on which files they cover.
    """
    offenders = []
    for path, rel in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if marker.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    return offenders


def test_no_stale_rc_or_pre_ga_citations():
    offenders = _offending_lines(_STALE_MARKERS)
    assert not offenders, (
        "Stale pre-GA AdCP citations found (GA 3.1.0/3.1.1 are published). "
        "Refresh these to cite the GA storyboard:\n" + "\n".join(offenders)
    )


def test_no_citations_under_the_dangling_prose_root():
    offenders = _offending_lines(_DANGLING_PROSE_ROOT)
    assert not offenders, (
        "Citation(s) under a spec prose root that resolves at no tag. "
        "dist/docs/ stops at 3.1.0, so dist/docs/3.1.1/<path> cannot be read at "
        "v3.1.1. Prose for the pinned version lives in the repository-root docs/ "
        "tree at the tag — for example docs/protocol/get_adcp_capabilities.mdx. "
        "Verify the replacement with `git cat-file -e v3.1.1:<path>` before "
        "relying on it, and re-derive any line anchors against the new file "
        "rather than carrying the old ones over:\n" + "\n".join(offenders)
    )


def test_the_dangling_root_marker_still_matches_a_citation():
    """The marker must match a real citation, or its green means nothing.

    A citation guard that matches nothing passes for the same reason a broken
    one does. This pins the discriminator in BOTH directions against the exact
    lines that motivated it: the pre-fix BR-UC-010 citation form must match,
    and the two in-scan-root warning forms must not.
    """
    cited = "    # @source repo=adcp ref=v3.2.1 path=dist/docs/3.1.1/building/implementation/x.mdx (L23)"
    assert _DANGLING_PROSE_ROOT.search(cited), "marker no longer matches a known-bad citation"

    for warning in (
        "does not: `dist/docs/` stops at `3.1.0`, so `dist/docs/3.1.1/` resolves at no tag. Prose",
        "``v3.1.1:docs/building/by-layer/L1/security.mdx`` (there is no ``dist/docs/3.1.1/`` at",
    ):
        assert not _DANGLING_PROSE_ROOT.search(warning), f"marker reddens a warning form: {warning}"

    for resolving in (
        "``dist/docs/3.1.0/reference/url-canonicalization.mdx``",
        "``dist/docs/3.1.0-rc.15/building/by-layer/L1/security.mdx``",
        "# dist/docs/3.1.0-beta.3/ tree",
    ):
        assert not _DANGLING_PROSE_ROOT.search(resolving), f"marker reddens a resolving root: {resolving}"


# ---------------------------------------------------------------------------
# Current-tense pin claims must not exist — the pin is pointed at, not restated
# ---------------------------------------------------------------------------

# A version token: 3.1.1, 6.6.0, 3.1.0-beta.3, …
# Two prerelease spellings, because the two things this guard reads version numbers
# out of use different ones. The AdCP SPEC version is SemVer and hyphenates
# (``3.1.0-beta.3``); the adcp SDK version is a Python package version and PEP 440
# attaches the prerelease with no separator (``9.0.0b1``, which release-please emits
# for the beta series). Matching only the hyphen form made this guard read
# ``adcp==9.0.0b1`` as a claim of ``9.0.0``, compare that against the real pin, and
# report every correct file as stale -- its own two detector tests failed with it,
# which is what identified the guard rather than the files as wrong.
_VERSION = r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:a|b|c|rc)[0-9]+)?(?:-[A-Za-z0-9.]+)?"

# Claim forms. Each requires a present-tense connective binding THIS project to
# a version — "targets X", "via the adcp==X SDK", "(an) implementation of …
# (AdCP X)". Past-tense prose, release notes and era references carry none of
# these connectives and are therefore not claims. ``kind`` selects which pin the
# captured version is graded against.
_SPEC = "spec"
_SDK = "sdk"

_PIN_CLAIM_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "targets-adcp-spec",
        _SPEC,
        re.compile(rf"\btargets?\s+(?:the\s+)?AdCP(?:\s+spec)?(?:\s+version)?\s+({_VERSION})"),
    ),
    (
        "implementation-of-adcp",
        _SPEC,
        re.compile(rf"\bimplementation\s+of\s+[^.]{{0,120}}?\(\s*AdCP\s+({_VERSION})\s*\)"),
    ),
    (
        "via-the-adcp-sdk",
        _SDK,
        re.compile(rf"\bvia\s+the\s+adcp==({_VERSION})"),
    ),
)

# Markdown emphasis / code fencing / blockquote markers are replaced by a SPACE
# (never deleted) so match offsets still map to real line numbers, while
# "AdCP spec **3.1.1**" and "`adcp==6.6.0`" read as plain prose to the patterns.
_MARKUP_NOISE = str.maketrans({"*": " ", "`": " ", "_": " ", ">": " "})

_PIN_CLAIM_SUFFIXES = _TEXT_SUFFIXES | {".toml", ".mdc"}


class PinClaim(NamedTuple):
    """A present-tense assertion about which AdCP spec / SDK this project targets."""

    lineno: int
    pattern: str
    kind: str
    version: str
    line: str


def iter_pin_claims(text: str) -> Iterator[PinClaim]:
    """Yield every present-tense pin claim in *text*, with the line it sits on."""
    normalized = text.translate(_MARKUP_NOISE)
    lines = text.splitlines()
    for name, kind, pattern in _PIN_CLAIM_PATTERNS:
        for match in pattern.finditer(normalized):
            # Line of the VERSION token, not of the sentence start: README wraps
            # its claim across two lines and the version is on the second.
            lineno = normalized.count("\n", 0, match.start(1)) + 1
            source_line = lines[lineno - 1].strip() if lineno <= len(lines) else ""
            yield PinClaim(lineno, name, kind, match.group(1), source_line)


#: The ONE document allowed to spell the spec version in prose, because
#: documenting the pin is its job and every other document links to it.
#:
#: Not a violation allowlist — a single named owner, and the claim it carries is
#: graded rather than exempted: :func:`pinned_version` parses this same sentence
#: and raises when it disagrees with ``adcp.get_adcp_spec_version()``. The SDK
#: version has no prose owner at all; ``pyproject.toml`` is its only home.
_SPEC_CLAIM_OWNER = Path("docs/adcp-spec-version.md")


def pinned_spec_version() -> str:
    """The AdCP spec version this repo pins, off the installed SDK.

    Raises if :data:`_SPEC_CLAIM_OWNER` documents a different one — that check
    lives in ``pinned_version()`` and is the owner document's grader.
    """
    return pinned_version(REPO_ROOT)


def _offending_pin_claims(rel: Path, text: str) -> list[str]:
    """Pin claims in *text* that restate a version where a pointer belongs."""
    offenders = []
    for claim in iter_pin_claims(text):
        if claim.kind == _SDK:
            reason = "restates the SDK version; pyproject.toml's `adcp==` line is its only home"
        elif rel != _SPEC_CLAIM_OWNER:
            reason = f"restates the spec version; only {_SPEC_CLAIM_OWNER} states it, everything else links to it"
        else:
            continue  # the owner's own claim, graded by pinned_version() raising
        offenders.append(f"{rel}:{claim.lineno}: {reason} [{claim.pattern}] {claim.line}")
    return offenders


def _pin_claim_files():
    for path in iter_git_tracked_files(REPO_ROOT):
        if path.resolve() == _THIS_FILE:
            continue  # this guard names the claim forms on purpose
        if path.is_symlink():
            continue  # e.g. AGENTS.md -> CLAUDE.md: same bytes, one fix site
        if path.suffix not in _PIN_CLAIM_SUFFIXES:
            continue
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        yield path, rel


def test_no_document_restates_the_pin():
    """The pin is pointed at, never copied — one owner for the spec version, none for the SDK."""
    offenders: list[str] = []
    owner_claims: list[PinClaim] = []
    for path, rel in _pin_claim_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        offenders.extend(_offending_pin_claims(rel, text))
        if rel == _SPEC_CLAIM_OWNER:
            owner_claims = [claim for claim in iter_pin_claims(text) if claim.kind == _SPEC]

    # Non-vacuity, and it is the real obligation rather than a count: the owner
    # document must still CARRY the sentence, both because it is the one
    # documented spelling of the spec version and because pinned_version() and
    # .claude/skills/prime/SKILL.md both read it. A total-claim counter would be
    # satisfied by any claim anywhere, including one this test wants refused.
    assert owner_claims, (
        f"non-vacuity: {_SPEC_CLAIM_OWNER} no longer states the spec version, so either the claim "
        "patterns have rotted or the one documented spelling of the pin was deleted. Restore the "
        "'targets **AdCP spec version <X>**' sentence — pinned_version() parses it and "
        ".claude/skills/prime/SKILL.md greps for it."
    )
    # Calling this grades the owner's claim: it raises when the sentence
    # disagrees with the installed wheel.
    expected_spec = pinned_spec_version()

    assert not offenders, (
        f"A document restates the pin instead of pointing at it (spec {expected_spec}).\n"
        "The pin has two homes and prose is not one of them: pyproject.toml's `adcp==` line for\n"
        f"the SDK, and adcp.get_adcp_spec_version() for the spec — spelled once, in\n"
        f"{_SPEC_CLAIM_OWNER}. Replace the version with a link to that document, or with the\n"
        "command that resolves it; do not re-pin the copy:\n" + "\n".join(offenders)
    )


def test_detector_sees_every_claim_form_and_ignores_history():
    """Meta-case for the detector: the three claim forms match, historical prose does not."""
    spec = pinned_spec_version()
    text = "\n".join(
        [
            # Historical / dated records — no present-tense claim connective.
            "The original setup used `mirrors-mypy` with `additional_dependencies: [adcp==3.2.0]`.",
            "- **Spec target** — `adcp==5.7.0`, AdCP spec `3.1.0-beta.3`, pinned in `pyproject.toml`.",
            "adcontextprotocol/adcp@04f59d2d5 / tag v3.1-04f59d2d5, the 3.1.0-beta.3 era",
            "Pins `adcp==5.7.0` (was 4.3.0); `EXPECTED_SPEC_VERSION` -> `3.1.0-beta.3`.",
            # Present-tense claims, naming the ACTUAL pin — detected all the same.
            f"Prebid Sales Agent targets **AdCP spec version {spec}**.",
            f"This project targets AdCP spec **{spec}** via the `adcp==9.9.9b9` Python SDK.",
            "> A pre-1.0 implementation of a pre-release protocol",
            f"> (AdCP {spec}), under active development.",
        ]
    )

    claims = list(iter_pin_claims(text))

    # The SDK token is deliberately not the pin: under this guard ANY version in
    # that position is refused, so which one it names is immaterial — and writing
    # the real one here would reintroduce the local-segment comparison the
    # inversion deleted.
    assert [(c.lineno, c.pattern) for c in claims] == [
        (5, "targets-adcp-spec"),
        (6, "targets-adcp-spec"),
        (8, "implementation-of-adcp"),
        (6, "via-the-adcp-sdk"),
    ], f"detector must see the four present-tense claims and only those: {[(c.lineno, c.pattern) for c in claims]}"


def test_a_restated_pin_is_an_offense_even_when_it_names_the_right_version():
    """The inversion itself: a CORRECT copy is refused, and only the owner may spell the spec version."""
    spec = pinned_spec_version()
    correct_sentence = f"This project targets AdCP spec **{spec}** via the `adcp==9.9.9b9` Python SDK."

    elsewhere = _offending_pin_claims(Path("CLAUDE.md"), correct_sentence)
    assert [o.split(": ", 1)[1].split(";")[0] for o in elsewhere] == [
        "restates the spec version",
        "restates the SDK version",
    ], f"a correct copy outside the owner must be refused on both counts: {elsewhere}"

    # In the owner document the spec claim is the documented one and passes; the
    # SDK half is still refused there, because no document states it.
    in_owner = _offending_pin_claims(_SPEC_CLAIM_OWNER, correct_sentence)
    assert [o.split(": ", 1)[1].split(";")[0] for o in in_owner] == ["restates the SDK version"], (
        f"the owner may state the spec version and no document may state the SDK version: {in_owner}"
    )
