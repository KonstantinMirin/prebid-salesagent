"""Shared walk over a run's per-suite JSON reports.

Both report checkers ask the same question of a results directory -- "read every
suite's summary, and tell me which suites are a problem" -- and differ only in
what counts as a problem. The walk, and the rule that an unreadable report is
itself a finding rather than something to skip, live here so the two cannot
drift apart.
"""

from __future__ import annotations

import glob
import json
import os
from collections.abc import Callable, Iterable


def scan_suite_summaries(
    results_dir: str,
    inspect: Callable[[str, dict], Iterable[str]],
) -> list[str]:
    """Return one problem line per finding, empty when every suite is clean.

    ``inspect`` receives a suite's report name and its ``summary`` mapping, and
    returns any problem lines for that suite. A report that cannot be read is
    reported here rather than passed to ``inspect``: a run whose evidence is
    unreadable has not been shown to pass.
    """
    problems: list[str] = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as handle:
                summary = json.load(handle).get("summary", {})
        except Exception as exc:  # noqa: BLE001 -- an unreadable report is itself a finding
            problems.append(f"  {name}: unreadable ({exc})")
            continue
        problems.extend(inspect(name, summary))
    return problems
