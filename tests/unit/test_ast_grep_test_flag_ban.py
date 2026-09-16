"""Executable meta-test for the test-flag ast-grep ban.

The ENFORCEMENT is the rule, not this module. It lives at
``.ast-grep/rules/test-flag-never-reaches-production.yml``, is discovered through
``sgconfig.yml``'s ``ruleDirs``, and runs on the ``make quality`` /
``make quality-ci`` ``ast-grep scan`` line. This module stands to it exactly as
``tests/unit/test_ast_grep_credential_header_ban.py`` stands to the credential-header
ban: it proves the ban FIRES, that it is BUILD-FAILING, and that its one exemption is
live rather than prose. It deliberately does not re-implement the detection — a second
AST walk written here would be a divergent copy of the rule, and the rule is the gate.

WHAT THE RULE REFUSES. Any read of ``adcp_testing`` under ``src/``. The flag says a
suite is running and nothing about the seller being served, so a production path that
branches on it serves a different seller under test than in deployment — which makes the
suite's verdict conditional on the suite being what ran it. CLAUDE.md pattern 11 carries
the reasoning and the two fixes, neither of which is the fork.

THE EXEMPTION. ``src/core/config.py``, because it declares the field. Case (d) below is
what keeps that from becoming a hiding place: the file must actually contain reads, and
the properties doing the reading are pinned shrink-only by
``tests/unit/test_test_flag_properties_only_shrink.py``. GH #2255 owns emptying them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.unit._architecture_helpers import repo_root

RULE_ID = "test-flag-never-reaches-production"
RULE_FILE = f".ast-grep/rules/{RULE_ID}.yml"

#: A production read of the flag, in the spelling every real site uses: an attribute chain
#: off a settings object. Written to a temp file under src/ so the rule's own ``files:``
#: scoping applies to it exactly as it would to a real module.
_VIOLATING_SOURCE = """\
from src.core.config import get_settings


def choose_behavior() -> str:
    if get_settings().testing.adcp_testing:
        return "the test answer"
    return "the real answer"
"""

#: The same decision taken on a real input. This is what the rule steers toward, so it
#: must NOT match — a negative case that fails would make the rule unusable.
_CONFORMING_SOURCE = """\
from src.core.config import get_settings


def choose_behavior() -> str:
    if get_settings().adapters.mock_adapter_selected:
        return "the mock adapter's answer"
    return "the real answer"
"""


def _ast_grep_bin() -> Path:
    """The venv-local ast-grep — what ``uv run ast-grep`` resolves to, and nothing else.

    Resolved next to ``sys.executable`` rather than through PATH for the reason the
    credential-header module records: a PATH lookup finds a homebrew binary that exists on
    a developer machine and not in CI, so this module would pass locally while the gate
    line it grades failed there. Absence FAILS rather than skips, for the same reason.
    """
    candidate = Path(sys.executable).parent / "ast-grep"
    assert candidate.exists(), (
        f"{candidate} does not exist: ast-grep is not installed in this environment's venv. "
        "Declare `ast-grep-cli` in the pyproject dev group so `uv run ast-grep` resolves."
    )
    return candidate


def _scan(*paths: str) -> subprocess.CompletedProcess[str]:
    """Run the real ast-grep with the real rule file over *paths*, from the repo root."""
    return subprocess.run(
        [str(_ast_grep_bin()), "scan", "--rule", RULE_FILE, *paths, "--json=compact"],
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )


def _matches(proc: subprocess.CompletedProcess[str]) -> list[dict]:
    """Parse ast-grep's compact JSON, refusing any exit code that means it did not run.

    The anti-vacuity gate for every case here. ast-grep exits 6 when ``--rule`` names a
    file it cannot read, printing nothing on stdout — so an absent or unparseable rule
    parses as "no matches" and every negative-shaped assertion below would pass while
    grading nothing. Only 0 (clean) and 1 (violations found) mean the rule executed.
    """
    assert proc.returncode in (0, 1), (
        f"ast-grep exited {proc.returncode}, which means it did not run the rule "
        f"(6 = rule file unreadable, 3 = filter matched no rule).\n"
        f"stdout={proc.stdout[:400]!r}\nstderr={proc.stderr[:400]!r}"
    )
    # ``--json=compact`` emits ONE JSON array, not one object per line: a clean scan prints
    # "[]". Parsing line-by-line made a clean scan read as a single empty-list "match".
    return json.loads(proc.stdout or "[]")


@pytest.fixture
def planted() -> Iterator[Path]:
    """A directory under ``src/`` the cases write probe modules into.

    Under ``src/`` deliberately: the rule is scoped ``files: ["src/**/*.py"]``, so a probe
    written to a pytest tmp_path would sit outside that glob and prove nothing about a
    production read — the scan would report clean whether the rule worked or not. Cleaned
    explicitly on teardown, since it cannot live under tmp_path.
    """
    target = repo_root() / "src" / "_ast_grep_probe"
    target.mkdir(exist_ok=True)
    yield target
    for child in target.iterdir():
        child.unlink()
    target.rmdir()


def test_a_production_read_of_the_flag_matches(planted: Path) -> None:
    """(a) POSITIVE — the rule sees the spelling every real site uses."""
    probe = planted / "reads_the_flag.py"
    probe.write_text(_VIOLATING_SOURCE, encoding="utf-8")

    found = _matches(_scan(str(probe.relative_to(repo_root()))))

    assert len(found) == 1, f"expected exactly one match for one read, got {len(found)}: {found}"
    assert found[0]["ruleId"] == RULE_ID
    assert "adcp_testing" in found[0]["text"]


def test_the_match_is_build_failing(planted: Path) -> None:
    """(b) BUILD-FAILING — a violation exits non-zero.

    Without ``severity: error`` ast-grep prints its matches and exits 0, and a rule that
    reports while passing is the dormancy every guard here exists to remove.
    """
    probe = planted / "reads_the_flag.py"
    probe.write_text(_VIOLATING_SOURCE, encoding="utf-8")

    assert _scan(str(probe.relative_to(repo_root()))).returncode == 1


def test_the_same_decision_on_a_real_input_is_clean(planted: Path) -> None:
    """(c) NEGATIVE — reading a settings field a deployment can set is the fix, not a finding."""
    probe = planted / "reads_a_real_input.py"
    probe.write_text(_CONFORMING_SOURCE, encoding="utf-8")

    proc = _scan(str(probe.relative_to(repo_root())))

    assert _matches(proc) == []
    assert proc.returncode == 0


def test_the_config_exemption_is_live_not_prose() -> None:
    """(d) EXEMPTION LIVE — config.py is exempt AND actually contains reads.

    An exemption for a file that no longer violates is a stale entry pretending to be a
    decision. This asserts the file still holds reads (so the exemption has a subject) and
    that the rule nonetheless reports nothing for it (so the exemption is in force).
    """
    config = repo_root() / "src" / "core" / "config.py"
    assert "adcp_testing" in config.read_text(encoding="utf-8"), (
        "src/core/config.py no longer reads adcp_testing, so its `ignores:` entry in "
        f"{RULE_FILE} has no subject and must be deleted — with it gone the ban needs no "
        "exemption at all, which is the outcome GH #2255 is for."
    )

    proc = _scan("src/core/config.py")

    assert _matches(proc) == [], "the config.py exemption is not in force"
    assert proc.returncode == 0


def _tracked_production_modules() -> list[str]:
    """Every ``.py`` file under ``src/`` that git tracks.

    Case (e)'s subject is the COMMITTED tree, so it asks git rather than scanning the
    working directory. Scanning ``src/`` outright made the case sensitive to any stray
    local file — including the probe cases (a)-(c) plant under ``src/_ast_grep_probe/``,
    which on a serial run is cleaned up before this case sees it and under xdist is not:
    the probe lands on one worker while this case scans on another, and the guard fails
    on its own fixture. A file nothing tracks is by definition not a production path.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z", "src/"],
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=True,
    )
    modules = [p for p in listed.stdout.split("\0") if p.endswith(".py")]
    assert modules, "git tracks no .py files under src/, so this case has no subject"
    return modules


def test_the_tree_is_clean_under_the_rule() -> None:
    """(e) THE LIVE TREE — no production file outside the exemption reads the flag."""
    proc = _scan(*_tracked_production_modules())

    assert _matches(proc) == [], (
        "a production path reads adcp_testing. Give the behavior a real input a deployment "
        "can set (a tenant column, an AdapterConfig row, a settings field) and let the test "
        "seed it — CLAUDE.md pattern 11."
    )
    assert proc.returncode == 0
