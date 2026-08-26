"""Opt-in per-worker timing profile, to explain where a parallel run's wall clock goes.

Motivation: after #2006 made the unit suite parallel, the largest remaining cost
in every suite was NOT test execution. Derived from the run reports, per-worker
"busy" time (the sum of each test's setup+call+teardown) accounts for only
42--73% of a suite's wall clock:

    suite            box   wall     busy/worker   unaccounted
    bdd_inprocess    A     640.4s   392.5s        247.9s  (39%)
    bdd_inprocess    B     652.4s   401.4s        251.0s  (38%)
    bdd_e2e          B     353.3s   147.4s        205.9s  (58%)
    unit             B     215.2s    99.7s        115.5s  (54%)

That residual is the thing to attack, but "wall minus busy" is a subtraction, not
a measurement -- it lumps interpreter start, application import, collection and
end-of-run scheduling idle into one number and cannot say which dominates. Since
every xdist worker imports and collects INDEPENDENTLY, the residual plausibly
scales with worker count, which would mean adding workers is negative-yield past
some point. That is a claim worth measuring rather than assuming.

This plugin measures it directly, per worker:

    import    plugin import -> pytest_configure   (interpreter + plugin/conftest
                                                   imports, incl. the app)
    collect   collection start -> finish          (+ the item count)
    idle      time inside the test loop NOT spent in a test  (scheduling gaps,
                                                   and the tail while other
                                                   workers still have work)
    tests     sum of this worker's own test durations

Off unless ``PYTEST_WORKER_PROFILE`` names a directory, and when off costs one
environment lookup at import. Each worker writes ``<dir>/<workerid>.json``;
``summarise()`` aggregates a directory into per-phase totals.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# Import time is the earliest point this plugin can observe. Everything before it
# (interpreter boot, pytest's own bootstrap) is invisible and is reported
# separately as the gap against the process's own start time where available.
_T_IMPORT = time.time()

_OUT_DIR = os.environ.get("PYTEST_WORKER_PROFILE")

_marks: dict[str, float] = {}
_counts: dict[str, int] = {}
_test_seconds = 0.0

enabled = bool(_OUT_DIR)


def _mark(name: str) -> None:
    _marks[name] = time.time()


def on_collection_start() -> None:
    if enabled:
        _mark("collect_start")


def on_collection_finish(item_count: int) -> None:
    if not enabled:
        return
    _mark("collect_finish")
    _counts["collected"] = item_count


def on_loop_start() -> None:
    if enabled:
        _mark("loop_start")


def record_test_duration(seconds: float) -> None:
    """Accumulate this worker's own execution time, phase by phase."""
    if enabled:
        global _test_seconds
        _test_seconds += seconds or 0.0


def on_session_finish() -> None:
    if not enabled:
        return
    _mark("finish")
    out = Path(_OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    collect_start = _marks.get("collect_start", _T_IMPORT)
    collect_finish = _marks.get("collect_finish", collect_start)
    loop_start = _marks.get("loop_start", collect_finish)
    finish = _marks["finish"]

    # `idle` is the residual inside the test loop: scheduling gaps plus the tail
    # this worker spends with nothing left to run while others finish. It is the
    # part a better DISTRIBUTION fixes; `import`/`collect` are the parts only a
    # cheaper startup fixes. Keeping them apart is the whole point.
    record = {
        "worker": worker,
        "collected": _counts.get("collected", 0),
        "import_s": round(collect_start - _T_IMPORT, 3),
        "collect_s": round(collect_finish - collect_start, 3),
        "tests_s": round(_test_seconds, 3),
        "idle_s": round(max(0.0, (finish - loop_start) - _test_seconds), 3),
        "worker_wall_s": round(finish - _T_IMPORT, 3),
    }
    (out / f"{worker}.json").write_text(json.dumps(record), encoding="utf-8")


def summarise(directory: str | Path) -> dict[str, Any]:
    """Aggregate a profile directory. Importable from a script or a REPL.

    The xdist CONTROLLER writes a record too (``main``), and it must not be
    averaged with the workers: it collects like they do but executes nothing, so
    folding it in would understate per-worker test time and overstate idle.
    """
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.json"))]
    if not records:
        return {"workers": 0}
    workers = [r for r in records if r["worker"] != "main"] or records
    controller = next((r for r in records if r["worker"] == "main"), None)
    n = len(workers)

    def total(key: str) -> float:
        return round(sum(r[key] for r in workers), 1)

    summary = {
        "workers": n,
        "collected_per_worker": workers[0]["collected"],
        # Summed across workers: what the machine actually spent on each phase.
        "import_s_total": total("import_s"),
        "collect_s_total": total("collect_s"),
        "tests_s_total": total("tests_s"),
        "idle_s_total": total("idle_s"),
        # Per worker: this is what does NOT shrink by adding workers, and is the
        # number that decides whether more workers still pay for themselves.
        "startup_per_worker_s": round(sum(r["import_s"] + r["collect_s"] for r in workers) / n, 1),
        # The suite waits for its slowest worker, not for the average.
        "slowest_worker_wall_s": round(max(r["worker_wall_s"] for r in workers), 1),
    }
    if controller is not None:
        summary["controller_collect_s"] = controller["collect_s"]
        summary["controller_wall_s"] = controller["worker_wall_s"]
    return summary
