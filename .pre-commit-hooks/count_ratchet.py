"""Shared count-baseline ratchet driver for pre-commit / quality-ci hooks.

Extracted so type-ignore, duplication, ruff-complexity (and future mypy)
ratchets share one create / ``--update-baseline`` / compare / auto-lower
control flow (ADR-009 / #1613 review). Each hook keeps only its count
method; baseline codecs, CLI prelude, and tooling-failure guards live here.

A ratcheting baseline may only SHRINK, and enforcing that takes two compares,
not one:

1. ``current`` vs the committed baseline — every hook always had this;
2. the committed baseline vs an UPSTREAM ceiling — because the commit under
   test can also edit the baseline file, and (1) alone reads a raised baseline
   as the new truth.

(2) used to be an opt-in that four hooks each re-implemented as a ~40-line
near-copy and two — ``check_code_duplication`` and
``check_mypy_untyped_defs_count`` — never implemented at all.
``.mypy-untyped-defs-baseline`` was duly committed at 237 against a merge-base
value of 227 and rode through green. Two further paths in this module leaked
the same way regardless of the hook: ``baseline is None`` created the file at
today's count (so ``rm .type-ignore-baseline`` accepted any count), and
``--update-baseline`` rewrote it unconditionally.

So the ceiling probe is the DRIVER's, it is not optional, and it runs on every
path that can write — create, ``--update-baseline``, compare and auto-lower.
Growth is unrepresentable through the tooling rather than merely visible to a
reviewer; ``tests/unit/test_architecture_ratchet_hooks_use_driver.py`` keeps it
that way for hooks written later.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

#: Refs consulted for the upstream ceiling, in order. ``origin/main`` is what CI
#: compares against; the merge base is what a branch actually departed from, and
#: is the only reference that answers for a baseline main does not carry yet.
#: CI fetches main with ``--depth=1``, so the merge base is often unresolvable
#: there — the list is filtered to refs that resolve, never assumed.
MAIN_REF = "origin/main"


def read_json_baseline(baseline_file: Path, keys: Sequence[str]) -> dict[str, int] | None:
    """Load a JSON object baseline; missing keys default to 0."""
    if not baseline_file.exists():
        return None
    try:
        data = json.loads(baseline_file.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"baseline must be a JSON object, got {type(data).__name__}")
        return {key: int(data.get(key, 0)) for key in keys}
    except (ValueError, OSError, TypeError) as e:
        print(f"Warning: Could not read baseline from {baseline_file}: {e}", file=sys.stderr)
        return None


def write_json_baseline(baseline_file: Path, counts: Mapping[str, int], keys: Sequence[str]) -> None:
    """Write a JSON baseline with a stable key order."""
    payload = {key: int(counts[key]) for key in keys}
    baseline_file.write_text(json.dumps(payload, indent=2) + "\n")


def read_int_baseline(baseline_file: Path) -> int | None:
    """Load a single-integer baseline file."""
    if not baseline_file.exists():
        return None
    try:
        return int(baseline_file.read_text().strip())
    except (ValueError, OSError) as e:
        print(f"Warning: Could not read baseline from {baseline_file}: {e}", file=sys.stderr)
        return None


def write_int_baseline(baseline_file: Path, count: int) -> None:
    """Write a single-integer baseline file."""
    baseline_file.write_text(f"{count}\n")


def int_baseline_io(
    key: str,
) -> tuple[Callable[[Path], dict[str, int] | None], Callable[[Path, Mapping[str, int]], None]]:
    """Reader/writer pair for a single-integer baseline exposed as a one-key dict."""

    def read_baseline(baseline_file: Path) -> dict[str, int] | None:
        value = read_int_baseline(baseline_file)
        if value is None:
            return None
        return {key: value}

    def write_baseline(baseline_file: Path, counts: Mapping[str, int]) -> None:
        write_int_baseline(baseline_file, int(counts[key]))

    return read_baseline, write_baseline


def json_baseline_io(
    keys: Sequence[str],
) -> tuple[Callable[[Path], dict[str, int] | None], Callable[[Path, Mapping[str, int]], None]]:
    """Reader/writer pair for a multi-key JSON baseline."""

    def read_baseline(baseline_file: Path) -> dict[str, int] | None:
        return read_json_baseline(baseline_file, keys)

    def write_baseline(baseline_file: Path, counts: Mapping[str, int]) -> None:
        write_json_baseline(baseline_file, counts, keys)

    return read_baseline, write_baseline


def parse_ratchet_args(description: str) -> argparse.Namespace:
    """Shared argparse for count-ratchet hooks (``--update-baseline`` only)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Force update baseline to current count(s) (↑ must be justified in review)",
    )
    return parser.parse_args()


def resolve_ratchet_paths(
    *,
    baseline_name: str,
    src_dirname: str = "src",
) -> tuple[Path, Path, Path]:
    """Return ``(repo_root, src_path, baseline_file)``; exit 1 if ``src/`` is missing."""
    repo_root = Path(__file__).resolve().parent.parent
    src_path = repo_root / src_dirname
    if not src_path.exists():
        print(f"Error: {src_dirname}/ directory not found", file=sys.stderr)
        raise SystemExit(1)
    return repo_root, src_path, repo_root / baseline_name


def run_counting_tool(
    cmd: Sequence[str],
    *,
    cwd: Path,
    has_findings: Callable[[subprocess.CompletedProcess[str]], bool],
    label: str,
    truncate: int = 800,
) -> subprocess.CompletedProcess[str]:
    """Run a count tooling command; abort on fatal / empty-findings exit 1."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode not in (0, 1) or (result.returncode == 1 and not has_findings(result)):
        print(f"ERROR: {label} failed while counting:", file=sys.stderr)
        print((result.stderr or result.stdout or "")[:truncate], file=sys.stderr)
        raise SystemExit(2)
    return result


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True)


def _upstream_refs(repo_root: Path) -> list[str]:
    """Resolvable upstream references, most authoritative first.

    The MERGE BASE leads, because it is what this branch actually inherited,
    and a ratchet grades a branch against what it inherited. ``origin/main``
    alone cannot do that job once main moves on: main paying complexity down
    from 182 to 177 after a branch departs is main's progress, not the branch's
    regression, yet a naive origin/main compare reports the branch's untouched
    182 as a raise. Failures a branch cannot act on are how ``--update-baseline``
    becomes a habit — the very habit these ratchets exist to prevent.

    ``origin/main`` still follows, and carries real weight in two places: it
    answers for baselines and KEYS the merge base does not have, and in CI it is
    usually the only ref that resolves at all (the quality-gate job fetches main
    with ``--depth=1``, which leaves no common history to compute a merge base
    from). So the branch is graded on what it inherited, and the merged result is
    graded against main — which is the ref that is binding at merge time.
    """
    refs = []
    merge_base = _git(repo_root, "merge-base", "HEAD", MAIN_REF)
    if merge_base.returncode == 0 and merge_base.stdout.strip():
        refs.append(merge_base.stdout.strip())
    if _git(repo_root, "rev-parse", "--verify", "--quiet", f"{MAIN_REF}^{{commit}}").returncode == 0:
        refs.append(MAIN_REF)
    return refs


def _read_upstream_baseline(repo_root: Path, ref: str, baseline_name: str, parse: Callable[[str], object]) -> dict:
    """Decode ``<ref>:<baseline_name>``; ``{}`` when the ref lacks the file."""
    result = _git(repo_root, "show", f"{ref}:{baseline_name}")
    if result.returncode != 0:
        return {}
    try:
        decoded = parse(result.stdout)
    except (ValueError, TypeError) as e:
        print(f"ERROR: {ref}:{baseline_name} is not a valid baseline: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    if not isinstance(decoded, Mapping):
        print(f"ERROR: {ref}:{baseline_name} did not decode to a mapping", file=sys.stderr)
        raise SystemExit(1)
    return {str(key): int(value) for key, value in decoded.items()}


def _extract_upstream_tree(repo_root: Path, ref: str, paths: Sequence[str], dest: Path) -> Path:
    """Materialize ``ref``'s copy of ``paths`` under ``dest`` and return it."""
    archive = dest / "tree.tar"
    with archive.open("wb") as handle:
        # stdout is a real fd, so the child's bytes land in the file whatever
        # `text` says; text=True only decodes the captured stderr.
        result = subprocess.run(
            ["git", "archive", ref, *paths], cwd=repo_root, stdout=handle, stderr=subprocess.PIPE, text=True
        )
    if result.returncode != 0:
        raise RuntimeError(f"git archive {ref} failed: {(result.stderr or '')[:300]}")
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    archive.unlink()
    return dest


def resolve_upstream_ceiling(
    *,
    repo_root: Path,
    baseline_name: str,
    keys: Sequence[str],
    parse: Callable[[str], object],
    count_upstream: Callable[[Path], Mapping[str, int]] | None = None,
    upstream_paths: Sequence[str] = ("src", "tests", "scripts", "pyproject.toml"),
) -> dict[str, int]:
    """Highest value each key is allowed to hold, per upstream evidence.

    Evidence is consulted cheapest-first and per KEY, so a newly ratcheted key
    is not judged against a ceiling of 0 (its true count is pre-existing debt —
    that is why ``F841`` could join the ruff baseline at 39) while the keys
    upstream does track keep their real ceiling:

    1. the baseline file at the merge base — what this branch inherited;
    2. the baseline file committed on ``origin/main``, for keys (1) omits (and
       as the only available reference in CI's shallow checkout);
    3. ``count_upstream`` re-run against upstream SOURCE, for keys neither
       baseline carries. This is the branch that catches a ratchet whose
       baseline file is itself new — the shape that let
       ``.fixme-citation-baseline`` land seeded at ``tests_fixme_beads=4`` when
       the merge base's true count was 0.

    A key with no upstream evidence at all is OMITTED rather than defaulted:
    unmeasurable is not the same as unbounded, and the caller reports it.
    """
    refs = _upstream_refs(repo_root)
    ceiling: dict[str, int] = {}
    for ref in refs:
        upstream = _read_upstream_baseline(repo_root, ref, baseline_name, parse)
        for key in keys:
            if key not in ceiling and key in upstream:
                ceiling[key] = upstream[key]
        if all(key in ceiling for key in keys):
            return ceiling

    if count_upstream is None or not refs:
        return ceiling

    source_ref = refs[0]
    with tempfile.TemporaryDirectory(prefix="ratchet-upstream-") as tmp:
        try:
            tree = _extract_upstream_tree(repo_root, source_ref, upstream_paths, Path(tmp))
            counted = count_upstream(tree)
        except (RuntimeError, OSError, tarfile.TarError) as e:
            print(f"Warning: could not count {source_ref}'s source for {baseline_name}: {e}", file=sys.stderr)
            return ceiling
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    for key in keys:
        if key not in ceiling and key in counted:
            ceiling[key] = int(counted[key])
    return ceiling


def check_against_ceiling(
    *,
    keys: Sequence[str],
    probe: Mapping[str, int],
    ceiling: Mapping[str, int],
    baseline_name: str,
    format_key: Callable[[str], str],
    err: TextIO,
) -> int:
    """Fail when any probed value exceeds its upstream ceiling."""
    raised = [(key, probe[key], ceiling[key]) for key in keys if key in ceiling and probe[key] > ceiling[key]]
    if not raised:
        return 0
    print(f"{baseline_name} raised above upstream!", file=err)
    for key, value, limit in raised:
        print(f"  {format_key(key)}: upstream={limit} local={value} (+{value - limit})", file=err)
    print("", file=err)
    print("A ratcheting baseline may only SHRINK. Fix the new violations", file=err)
    print("instead of raising the baseline — and note that neither deleting", file=err)
    print("the baseline file nor --update-baseline gets around this probe.", file=err)
    return 1


def format_counts(counts: Mapping[str, int], keys: Sequence[str]) -> str:
    return ", ".join(f"{key}={counts[key]}" for key in keys)


def run_count_ratchet(
    *,
    keys: Sequence[str],
    current: Mapping[str, int],
    baseline_file: Path,
    update_baseline: bool,
    read_baseline: Callable[[Path], dict[str, int] | None],
    write_baseline: Callable[[Path, Mapping[str, int]], None],
    increase_header: str,
    increase_hints: Sequence[str],
    repo_root: Path | None = None,
    parse_upstream: Callable[[str], object] | None = None,
    count_upstream: Callable[[Path], Mapping[str, int]] | None = None,
    format_key: Callable[[str], str] | None = None,
    unit: str = "",
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Create / update / compare / auto-lower a multi-key count baseline.

    Returns a process exit code (0 ok, 1 regression).
    ``out`` / ``err`` default to ``None`` and resolve at call time so tests can
    inject ``io.StringIO`` (defaults bound at def-time shadow ``sys.stdout``).

    Before ANY write, the committed baseline is probed against the upstream
    ceiling (see ``resolve_upstream_ceiling``). The probed value differs per
    path, and each choice is what makes that path un-launderable:

    - create (no baseline file) and ``--update-baseline`` probe ``current``,
      because ``current`` is what is about to be written;
    - the normal compare probes ``min(baseline, current)``, so an auto-lower
      cannot mask a committed raise and a failed probe never writes.
    """
    out_stream = sys.stdout if out is None else out
    err_stream = sys.stderr if err is None else err
    label = format_key or (lambda key: key)
    unit_suffix = f" {unit}" if unit else ""

    baseline = read_baseline(baseline_file)
    writes_current = baseline is None or update_baseline
    probe = dict(current) if writes_current else {key: min(baseline.get(key, 0), current[key]) for key in keys}
    ceiling = resolve_upstream_ceiling(
        repo_root=repo_root if repo_root is not None else baseline_file.resolve().parent,
        baseline_name=baseline_file.name,
        keys=keys,
        parse=parse_upstream if parse_upstream is not None else json.loads,
        count_upstream=count_upstream,
    )
    if (
        check_against_ceiling(
            keys=keys,
            probe=probe,
            ceiling=ceiling,
            baseline_name=baseline_file.name,
            format_key=label,
            err=err_stream,
        )
        != 0
    ):
        return 1

    if baseline is None:
        print(
            f"No baseline found. Creating {baseline_file.name}: {format_counts(current, keys)}",
            file=out_stream,
        )
        write_baseline(baseline_file, current)
        return 0

    if update_baseline:
        print(
            f"Updating baseline: {format_counts(baseline, keys)} -> {format_counts(current, keys)}",
            file=out_stream,
        )
        write_baseline(baseline_file, current)
        return 0

    failed = False
    for key in keys:
        base = baseline.get(key, 0)
        cur = current[key]
        display = label(key)
        if cur > base:
            print(
                f"  {display}: {cur}{unit_suffix} (+{cur - base} NEW vs baseline {base})",
                file=err_stream,
            )
            failed = True
        elif cur < base:
            print(
                f"  {display}: {cur}{unit_suffix} (-{base - cur} fixed vs baseline {base})",
                file=out_stream,
            )
        else:
            print(f"  {display}: {cur}{unit_suffix} (unchanged)", file=out_stream)

    if failed:
        print("", file=err_stream)
        print(increase_header, file=err_stream)
        for hint in increase_hints:
            print(hint, file=err_stream)
        return 1

    normalized_baseline = {key: baseline.get(key, 0) for key in keys}
    if dict(current) != normalized_baseline:
        print(f"Automatically updating {baseline_file.name}...", file=out_stream)
        write_baseline(baseline_file, current)

    return 0
