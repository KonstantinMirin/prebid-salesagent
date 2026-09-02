"""Unit tests for the shared count-ratchet driver (#1613 / ADR-009)."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_HOOKS = _REPO / ".pre-commit-hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _load(name: str):
    path = _HOOKS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


count_ratchet = _load("count_ratchet")
check_type_ignore_count = _load("check_type_ignore_count")
check_ruff_complexity_count = _load("check_ruff_complexity_count")
check_mypy_untyped_defs_count = _load("check_mypy_untyped_defs_count")


def _cp(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_count_ratchet_creates_missing_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "counts.json"
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 3},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda _p: None,
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        out=out,
        err=err,
    )

    assert rc == 0
    assert writes == [{"a": 3}]
    assert "Creating" in out.getvalue()


def test_run_count_ratchet_update_baseline_rewrites(tmp_path: Path) -> None:
    baseline = tmp_path / "counts.json"
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 9},
        baseline_file=baseline,
        update_baseline=True,
        read_baseline=lambda _p: {"a": 4},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        out=out,
        err=err,
    )

    assert rc == 0
    assert writes == [{"a": 9}]
    assert "Updating baseline" in out.getvalue()


def test_run_count_ratchet_increase_exits_without_write(tmp_path: Path) -> None:
    baseline = tmp_path / "counts.json"
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a", "b"),
        current={"a": 5, "b": 1},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda _p: {"a": 4, "b": 1},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="COUNTS UP",
        increase_hints=("hint-line",),
        out=out,
        err=err,
    )

    assert rc == 1
    assert writes == []
    assert "COUNTS UP" in err.getvalue()
    assert "hint-line" in err.getvalue()


def test_run_count_ratchet_decrease_auto_lowers(tmp_path: Path) -> None:
    baseline = tmp_path / "counts.json"
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 2},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda _p: {"a": 5},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        out=out,
        err=err,
    )

    assert rc == 0
    assert writes == [{"a": 2}]
    assert "Automatically updating" in out.getvalue()


def test_run_count_ratchet_all_equal_no_write(tmp_path: Path) -> None:
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a", "b"),
        current={"a": 1, "b": 2},
        baseline_file=tmp_path / "counts.json",
        update_baseline=False,
        read_baseline=lambda _p: {"a": 1, "b": 2},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        out=out,
        err=err,
    )

    assert rc == 0
    assert writes == []


def test_run_count_ratchet_mixed_up_down_fails_without_write(tmp_path: Path) -> None:
    baseline = tmp_path / "counts.json"
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a", "b"),
        current={"a": 6, "b": 0},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda _p: {"a": 5, "b": 2},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        out=out,
        err=err,
    )

    assert rc == 1
    assert writes == []


def test_read_json_baseline_rejects_non_object(tmp_path: Path) -> None:
    baseline = tmp_path / "bad.json"
    baseline.write_text("[227]\n", encoding="utf-8")
    assert count_ratchet.read_json_baseline(baseline, ("C901",)) is None


def test_read_json_baseline_reads_object(tmp_path: Path) -> None:
    baseline = tmp_path / "ok.json"
    baseline.write_text('{"C901": 1, "PLR0912": 2}\n', encoding="utf-8")
    assert count_ratchet.read_json_baseline(baseline, ("C901", "PLR0912", "PLR0915")) == {
        "C901": 1,
        "PLR0912": 2,
        "PLR0915": 0,
    }


def test_run_counting_tool_rc0_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _cp(stdout="ok", returncode=0)
    monkeypatch.setattr(count_ratchet.subprocess, "run", lambda *_a, **_k: expected)
    got = count_ratchet.run_counting_tool(
        ["true"],
        cwd=_REPO,
        has_findings=lambda _r: False,
        label="tool",
    )
    assert got is expected


def test_run_counting_tool_rc1_with_findings_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _cp(stdout="finding", returncode=1)
    monkeypatch.setattr(count_ratchet.subprocess, "run", lambda *_a, **_k: expected)
    got = count_ratchet.run_counting_tool(
        ["tool"],
        cwd=_REPO,
        has_findings=lambda r: bool((r.stdout or "").strip()),
        label="tool",
    )
    assert got is expected


def test_run_counting_tool_rc1_empty_findings_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(count_ratchet.subprocess, "run", lambda *_a, **_k: _cp(stdout="", returncode=1))
    with pytest.raises(SystemExit) as exc:
        count_ratchet.run_counting_tool(
            ["tool"],
            cwd=_REPO,
            has_findings=lambda r: bool((r.stdout or "").strip()),
            label="tool",
        )
    assert exc.value.code == 2


def test_run_counting_tool_rc2_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        lambda *_a, **_k: _cp(stdout="findings", returncode=2),
    )
    with pytest.raises(SystemExit) as exc:
        count_ratchet.run_counting_tool(
            ["tool"],
            cwd=_REPO,
            has_findings=lambda r: True,
            label="tool",
        )
    assert exc.value.code == 2


def test_count_rule_violations_tallies_selected_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        [
            {"code": "C901"},
            {"code": "C901"},
            {"code": "PLR0912"},
            {"code": "F841"},
            {"code": "OTHER"},
        ]
    )
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        lambda *_a, **_k: _cp(stdout=payload, returncode=1),
    )
    # Zero-fill from RULES so adding a ratcheted rule does not break the tally
    # assertion, while the per-code counts stay pinned.
    assert check_ruff_complexity_count.count_rule_violations(_REPO, _REPO / "src") == {
        **dict.fromkeys(check_ruff_complexity_count.RULES, 0),
        "C901": 2,
        "PLR0912": 1,
        "F841": 1,
    }


def test_count_rule_violations_empty_findings_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(count_ratchet.subprocess, "run", lambda *_a, **_k: _cp(stdout="", returncode=1))
    with pytest.raises(SystemExit) as exc:
        check_ruff_complexity_count.count_rule_violations(_REPO, _REPO / "src")
    assert exc.value.code == 2


def test_count_untyped_defs_errors_tallies_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = "\n".join(
        [
            "a.py:1: error: x",
            "noise without sentinel",
            "b.py:2: error: y",
            "c.py:3: note: not an error",
            "d.py:4: error: z",
        ]
    )
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        lambda *_a, **_k: _cp(stdout=stdout, returncode=1),
    )
    assert check_mypy_untyped_defs_count.count_untyped_defs_errors(_REPO) == 3


def test_count_untyped_defs_errors_zero_on_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(count_ratchet.subprocess, "run", lambda *_a, **_k: _cp(stdout="", returncode=0))
    assert check_mypy_untyped_defs_count.count_untyped_defs_errors(_REPO) == 0


def test_count_untyped_defs_errors_rc1_without_sentinel_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        lambda *_a, **_k: _cp(stdout="error: crash without sentinel", returncode=1),
    )
    with pytest.raises(SystemExit) as exc:
        check_mypy_untyped_defs_count.count_untyped_defs_errors(_REPO)
    assert exc.value.code == 2


def test_count_untyped_defs_errors_rc2_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        lambda *_a, **_k: _cp(stdout="a.py:1: error: x", returncode=2),
    )
    with pytest.raises(SystemExit) as exc:
        check_mypy_untyped_defs_count.count_untyped_defs_errors(_REPO)
    assert exc.value.code == 2


def test_mypy_main_tooling_failure_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path
    (repo / "src").mkdir()
    baseline = repo / ".mypy-untyped-defs-baseline"
    baseline.write_text("227\n", encoding="utf-8")
    before = baseline.read_text(encoding="utf-8")

    monkeypatch.setattr(
        check_mypy_untyped_defs_count,
        "resolve_ratchet_paths",
        lambda **_kwargs: (repo, repo / "src", baseline),
    )
    monkeypatch.setattr(
        check_mypy_untyped_defs_count,
        "parse_ratchet_args",
        lambda _description: type("Args", (), {"update_baseline": False})(),
    )
    monkeypatch.setattr(
        check_mypy_untyped_defs_count,
        "count_untyped_defs_errors",
        lambda _repo: (_ for _ in ()).throw(SystemExit(2)),
    )

    with pytest.raises(SystemExit) as exc:
        check_mypy_untyped_defs_count.main()
    assert exc.value.code == 2
    assert baseline.read_text(encoding="utf-8") == before


def test_ruff_complexity_rules_match_pyproject_ratchet_bucket() -> None:
    """S1: RULES must equal the pyproject 'Ratchet targets' ignore bucket."""
    text = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(
        r"# --- Ratchet targets \(count-ratcheted via \.ruff-complexity-baseline; ADR-009\) ---\n"
        r"(.*?)\n\s*# --- Permanently accepted",
        text,
        flags=re.DOTALL,
    )
    assert match, "pyproject.toml missing Ratchet targets / Permanently accepted headers"
    from_pyproject = tuple(re.findall(r'"([A-Z0-9]+)"', match.group(1)))
    assert check_ruff_complexity_count.RULES == from_pyproject


def test_ruff_complexity_thresholds_pinned_to_ruff_defaults() -> None:
    """N3/#1657: pin mccabe/pylint thresholds so baseline counts stay stable.

    A silent bump of max-complexity / max-branches / max-statements would
    auto-lower ``.ruff-complexity-baseline`` without a reviewable change.
    """
    with (_REPO / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    lint = data["tool"]["ruff"]["lint"]
    assert lint["mccabe"]["max-complexity"] == 10
    assert lint["pylint"]["max-branches"] == 12
    assert lint["pylint"]["max-statements"] == 50


# ---------------------------------------------------------------------------
# The anti-raise probe's semantics, re-expressed at its new home
# ---------------------------------------------------------------------------
#
# These obligations were previously pinned per hook, against
# check_type_ignore_count.raise_probe_value / check_ruff_complexity_count.
# check_baseline_not_raised — four near-copies of one rule. The rule is
# unchanged; it now lives once, in run_count_ratchet, so the two hooks that
# never had a copy are covered by the same tests.


@pytest.mark.parametrize(
    ("baseline", "current", "update_baseline", "ceiling", "expected_rc"),
    [
        # create (no baseline file) probes `current`
        (None, 10, False, 9, 1),
        (None, 10, False, 10, 0),
        # --update-baseline probes `current`
        (5, 10, True, 9, 1),
        (5, 10, True, 10, 0),
        # normal compare probes min(baseline, current): an auto-lower must not
        # mask a committed raise, and a count above a legal baseline is the
        # compare's business, not the probe's
        (8, 5, False, 5, 0),
        (12, 12, False, 11, 1),
    ],
)
def test_ceiling_probe_value_per_write_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    baseline: int | None,
    current: int,
    update_baseline: bool,
    ceiling: int,
    expected_rc: int,
) -> None:
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": ceiling})
    writes: list[dict[str, int]] = []

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": current},
        baseline_file=tmp_path / "counts.json",
        update_baseline=update_baseline,
        read_baseline=lambda _p: None if baseline is None else {"a": baseline},
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        repo_root=tmp_path,
        out=io.StringIO(),
        err=io.StringIO(),
    )

    assert rc == expected_rc
    if expected_rc == 1:
        assert writes == []


def test_compare_failure_is_not_reported_as_a_ceiling_breach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """min(baseline, current) keeps the two compares distinct.

    baseline=3 / current=9 against a ceiling of 3: the committed baseline is
    legal, so the probe must pass and the run must fail on the ordinary
    count-vs-baseline increase — reporting it as a raised baseline would send
    the author to edit the wrong thing.
    """
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": 3})
    err = io.StringIO()

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 9},
        baseline_file=tmp_path / "counts.json",
        update_baseline=False,
        read_baseline=lambda _p: {"a": 3},
        write_baseline=lambda _p, _counts: None,
        increase_header="count increased!",
        increase_hints=(),
        repo_root=tmp_path,
        out=io.StringIO(),
        err=err,
    )

    assert rc == 1
    assert "count increased!" in err.getvalue()
    assert "raised above upstream" not in err.getvalue()


def test_ceiling_applies_per_key_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key upstream never tracked stays landable; a tracked key stays guarded.

    Reading an untracked key as 0 would make every newly-ratcheted key
    unlandable — its true count IS the pre-existing debt, which is why F841
    could join the ruff baseline at 39. So an untracked key falls through to
    the next evidence source rather than defaulting.
    """
    tracked = json.dumps({"C901": 185, "PLR0912": 134, "PLR0915": 108})
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        _git_stub({("show", f"{count_ratchet.MAIN_REF}:.ruff-complexity-baseline"): _cp(stdout=tracked)}),
    )

    ceiling = count_ratchet.resolve_upstream_ceiling(
        repo_root=Path("/repo"),
        baseline_name=".ruff-complexity-baseline",
        keys=("C901", "PLR0912", "PLR0915", "F841"),
        parse=json.loads,
        count_upstream=lambda _tree: {"F841": 38},
    )

    assert ceiling == {"C901": 185, "PLR0912": 134, "PLR0915": 108}
    err = io.StringIO()
    landing = {"C901": 185, "PLR0912": 134, "PLR0915": 108, "F841": 38}
    assert (
        count_ratchet.check_against_ceiling(
            keys=tuple(landing),
            probe=landing,
            ceiling=ceiling,
            baseline_name=".ruff-complexity-baseline",
            format_key=str,
            err=err,
        )
        == 0
    )
    raising = {**landing, "C901": 186}
    assert (
        count_ratchet.check_against_ceiling(
            keys=tuple(raising),
            probe=raising,
            ceiling=ceiling,
            baseline_name=".ruff-complexity-baseline",
            format_key=str,
            err=io.StringIO(),
        )
        == 1
    )


def test_ruff_baseline_file_tracks_every_ratcheted_rule() -> None:
    """The committed baseline must carry a value for each RULES key.

    Missing keys read as 0 (read_json_baseline), so an unlisted rule would fail
    the ratchet on its real count the moment anyone runs the hook.
    """
    committed = json.loads((_REPO / ".ruff-complexity-baseline").read_text(encoding="utf-8"))

    assert set(committed) == set(check_ruff_complexity_count.RULES)


# ---------------------------------------------------------------------------
# Upstream ceiling: the anti-raise probe lives in the DRIVER, not per hook
# ---------------------------------------------------------------------------
#
# Five ratchets on this branch moved the wrong way, and every one of them was
# admitted by the same shape: the ratchet compared `current` against a baseline
# file that the same commit could edit, and the anti-raise probe that would have
# caught the edit was an OPT-IN each hook re-implemented (or, for
# check_code_duplication / check_mypy_untyped_defs_count, simply never did).
# `.mypy-untyped-defs-baseline` went 227 -> 237 through exactly that gap.
#
# The tests below pin the mechanism that makes the growth unrepresentable rather
# than merely noticed: `run_count_ratchet` resolves an upstream ceiling itself,
# on every path (create, --update-baseline, compare, auto-lower).


def _git_stub(table: dict[tuple[str, ...], subprocess.CompletedProcess[str]]):
    """Stub ``subprocess.run`` keyed on the git argv tail.

    ``rev-parse --verify`` of origin/main succeeds by default — every test here
    is about which baseline the ceiling comes from, not about a repo that has
    no main. Tables override ``show`` / ``merge-base``.
    """

    def runner(cmd, *_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        tail = tuple(cmd[1:])
        if tail in table:
            return table[tail]
        if tail[:1] == ("rev-parse",):
            return _cp(stdout="cafe1234\n")
        return _cp(returncode=128, stderr="fatal: not found")

    return runner


def test_upstream_ceiling_uses_origin_main_when_no_merge_base_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI fetches main with --depth=1, so origin/main is often the only ref."""
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        _git_stub({("show", "origin/main:.b"): _cp(stdout='{"a": 5}')}),
    )

    ceiling = count_ratchet.resolve_upstream_ceiling(
        repo_root=Path("/repo"), baseline_name=".b", keys=("a",), parse=json.loads
    )

    assert ceiling == {"a": 5}


def test_upstream_ceiling_prefers_the_merge_base_over_origin_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """A branch is graded against what it INHERITED, not against a moved-on main.

    main paying a count down after this branch departed is main's progress, not
    the branch's regression; grading the branch's untouched baseline against the
    lower number reports a raise the author cannot act on, which is how
    --update-baseline becomes reflex.
    """
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        _git_stub(
            {
                ("merge-base", "HEAD", "origin/main"): _cp(stdout="deadbeef\n"),
                ("show", "deadbeef:.b"): _cp(stdout='{"a": 182}'),
                ("show", "origin/main:.b"): _cp(stdout='{"a": 177}'),
            }
        ),
    )

    ceiling = count_ratchet.resolve_upstream_ceiling(
        repo_root=Path("/repo"), baseline_name=".b", keys=("a",), parse=json.loads
    )

    assert ceiling == {"a": 182}


def test_origin_main_answers_for_a_key_the_merge_base_omits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The merge base leads, but does not shadow keys it has no value for."""
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        _git_stub(
            {
                ("merge-base", "HEAD", "origin/main"): _cp(stdout="deadbeef\n"),
                ("show", "deadbeef:.b"): _cp(stdout='{"a": 5}'),
                ("show", "origin/main:.b"): _cp(stdout='{"a": 1, "b": 9}'),
            }
        ),
    )

    ceiling = count_ratchet.resolve_upstream_ceiling(
        repo_root=Path("/repo"), baseline_name=".b", keys=("a", "b"), parse=json.loads
    )

    assert ceiling == {"a": 5, "b": 9}


def test_upstream_ceiling_counts_upstream_source_for_untracked_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key no upstream baseline carries gets its ceiling from upstream SOURCE.

    This is what keeps a newly-ratcheted key landable (its true count is the
    pre-existing debt) WITHOUT handing it an unbounded seed.
    """
    monkeypatch.setattr(
        count_ratchet.subprocess,
        "run",
        _git_stub({("show", "origin/main:.b"): _cp(stdout='{"a": 5}')}),
    )
    monkeypatch.setattr(count_ratchet, "_extract_upstream_tree", lambda *_a, **_k: Path("/upstream"))

    ceiling = count_ratchet.resolve_upstream_ceiling(
        repo_root=Path("/repo"),
        baseline_name=".b",
        keys=("a", "b"),
        parse=json.loads,
        count_upstream=lambda root: {"a": 99, "b": 7} if root == Path("/upstream") else {},
    )

    assert ceiling == {"a": 5, "b": 7}


def test_upstream_ceiling_omits_key_with_no_upstream_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(count_ratchet.subprocess, "run", _git_stub({}))

    assert (
        count_ratchet.resolve_upstream_ceiling(
            repo_root=Path("/repo"), baseline_name=".b", keys=("a",), parse=json.loads
        )
        == {}
    )


def test_run_count_ratchet_rejects_baseline_above_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A committed baseline above upstream fails, and writes nothing."""
    baseline = tmp_path / "counts.json"
    baseline.write_text(json.dumps({"a": 237}), encoding="utf-8")
    writes: list[dict[str, int]] = []
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": 227})

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 237},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda p: json.loads(p.read_text()),
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        repo_root=tmp_path,
        out=out,
        err=err,
    )

    assert rc == 1
    assert writes == []
    assert "227" in err.getvalue()


def test_run_count_ratchet_ceiling_probes_the_update_baseline_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--update-baseline` cannot launder a raise: it probes the post-write value."""
    baseline = tmp_path / "counts.json"
    baseline.write_text(json.dumps({"a": 100}), encoding="utf-8")
    writes: list[dict[str, int]] = []
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": 100})

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 140},
        baseline_file=baseline,
        update_baseline=True,
        read_baseline=lambda p: json.loads(p.read_text()),
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        repo_root=tmp_path,
        out=io.StringIO(),
        err=io.StringIO(),
    )

    assert rc == 1
    assert writes == []


def test_run_count_ratchet_ceiling_probes_the_missing_baseline_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting the baseline file cannot launder a raise either.

    Without this, `baseline is None -> create at current, return 0` made every
    ratchet in the repo optional: `rm .type-ignore-baseline` accepted any count.
    """
    writes: list[dict[str, int]] = []
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": 10})

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 11},
        baseline_file=tmp_path / "absent.json",
        update_baseline=False,
        read_baseline=lambda _p: None,
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        repo_root=tmp_path,
        out=io.StringIO(),
        err=io.StringIO(),
    )

    assert rc == 1
    assert writes == []


def test_run_count_ratchet_auto_lower_still_allowed_under_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "counts.json"
    baseline.write_text(json.dumps({"a": 20}), encoding="utf-8")
    writes: list[dict[str, int]] = []
    monkeypatch.setattr(count_ratchet, "resolve_upstream_ceiling", lambda **_k: {"a": 20})

    rc = count_ratchet.run_count_ratchet(
        keys=("a",),
        current={"a": 12},
        baseline_file=baseline,
        update_baseline=False,
        read_baseline=lambda p: json.loads(p.read_text()),
        write_baseline=lambda _p, counts: writes.append(dict(counts)),
        increase_header="up",
        increase_hints=(),
        repo_root=tmp_path,
        out=io.StringIO(),
        err=io.StringIO(),
    )

    assert rc == 0
    assert writes == [{"a": 12}]
