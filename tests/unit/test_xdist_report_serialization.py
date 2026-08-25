"""An unserializable test report must not silently void an xdist session.

Background and the full measurement live in ``tests/_xdist_report_safety``.
In short: pytest copies ``report.__dict__`` onto the execnet wire and sanitizes
only three keys; execnet dispatches on EXACT type; and a ``DumpError`` on a
worker ends the whole session after reporting only the tests already collected
back, behind a summary line that says zero failures.

These tests pin three things:

1. the walker replaces exactly what execnet refuses and nothing else,
2. the result genuinely round-trips through **execnet's own serializer** rather
   than through this module's model of it,
3. end to end, a run that would otherwise be truncated reports every item -- and
   the control case proves that assertion is not vacuous.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from execnet.gateway_base import DumpError, dumps

from tests._xdist_report_safety import make_execnet_safe, sanitize_serialized_report

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. The walker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, 2**70, 1.5, complex(1, 2), "s", b"b", (), [], {}, set(), frozenset()],
    ids=repr,
)
def test_already_safe_values_are_returned_unchanged(value):
    """The common path must not rewrite a report that was already fine."""
    safe, offenders = make_execnet_safe(value)
    assert offenders == []
    assert safe == value
    assert type(safe) is type(value)


def test_unserializable_leaf_is_replaced_by_its_repr_and_named():
    mock = MagicMock()
    safe, offenders = make_execnet_safe({"leaked": mock})
    assert offenders == [".leaked = unittest.mock.MagicMock"]
    assert safe["leaked"] == repr(mock)


def test_offender_path_locates_the_value_inside_a_nested_report():
    """The reported path is the diagnostic — it must pinpoint the real key."""
    payload = {"_json_report_extra": {"call": {"log": [{"name": "x", "process": MagicMock()}]}}}
    _, offenders = make_execnet_safe(payload)
    assert offenders == ["._json_report_extra.call.log[0].process = unittest.mock.MagicMock"]


def test_subclasses_of_serializable_types_are_replaced_too():
    """execnet dispatches on exact type, so a str subclass is refused like a mock."""

    class Weird(str):
        pass

    safe, offenders = make_execnet_safe({"k": Weird("v")})
    assert offenders == [f".k = {Weird.__module__}.{Weird.__qualname__}"]
    with pytest.raises(DumpError):
        dumps({"k": Weird("v")})
    dumps(safe)


def test_container_subclasses_are_normalised_to_their_base_type():
    class WeirdList(list):
        pass

    safe, offenders = make_execnet_safe({"k": WeirdList([1, 2])})
    assert offenders == []
    assert type(safe["k"]) is list
    dumps(safe)


def test_cycles_terminate_instead_of_recursing_forever():
    payload: dict = {"name": "x"}
    payload["self"] = payload
    safe, offenders = make_execnet_safe(payload)
    assert offenders == [".self = <cycle> builtins.dict"]
    assert safe["name"] == "x"
    dumps(safe)


def test_depth_limit_terminates_a_pathological_structure():
    payload: dict = {}
    node = payload
    for _ in range(60):
        child: dict = {}
        node["n"] = child
        node = child
    safe, offenders = make_execnet_safe(payload)
    assert any("depth limit" in o for o in offenders)
    dumps(safe)


def test_a_repr_that_raises_does_not_become_a_second_crash():
    class Hostile:
        def __repr__(self):
            raise ValueError("no repr for you")

    safe, offenders = make_execnet_safe({"k": Hostile()})
    assert offenders == [f".k = {Hostile.__module__}.{Hostile.__qualname__}"]
    assert "unreprable" in safe["k"]
    dumps(safe)


# ---------------------------------------------------------------------------
# 2. Round-trip through execnet's own serializer
# ---------------------------------------------------------------------------


def test_a_realistic_polluted_report_fails_execnet_before_and_passes_after():
    """The load-bearing assertion: measured against execnet, not against a model of it.

    The payload is the real shape observed on this branch — pytest-json-report's
    ``_json_report_extra`` carrying ``dict(record.__dict__)`` for a log record
    whose ``process`` field is a mock because a leaked ``patch("os.getpid")``
    was live when the record was created.
    """
    report = {
        "nodeid": "tests/harness/test_harness_product.py::TestProductEnvContract::test_single_product",
        "outcome": "passed",
        "when": "call",
        "duration": 0.01,
        "sections": [],
        "user_properties": [],
        "_json_report_extra": {
            "call": {"log": [{"name": "src.core.tools.products", "levelname": "INFO", "process": MagicMock()}]}
        },
    }
    with pytest.raises(DumpError):
        dumps(report)
    with open(os.devnull, "w") as devnull:
        dumps(sanitize_serialized_report(report, nodeid=report["nodeid"], stream=devnull))


def test_sanitize_returns_the_same_object_when_nothing_needed_replacing():
    clean = {"nodeid": "t::x", "outcome": "passed", "sections": [], "user_properties": []}
    assert sanitize_serialized_report(clean) is clean


def test_an_offender_is_announced_and_never_dropped_silently():
    """Silence is the failure mode being fixed; a quiet mutation would miss the point."""
    import io

    stream = io.StringIO()
    payload = {"nodeid": "t::x", "_json_report_extra": {"call": {"log": [{"process": MagicMock()}]}}}
    out = sanitize_serialized_report(payload, nodeid="t::x", stream=stream)
    announced = stream.getvalue()
    assert "t::x" in announced
    assert "._json_report_extra.call.log[0].process" in announced
    assert "MagicMock" in announced
    assert out["_json_report_extra"]["call"]["log"][0]["process"].startswith("<MagicMock")


# ---------------------------------------------------------------------------
# 3. End to end, with a control
# ---------------------------------------------------------------------------

_POLLUTING_SUITE = """
import logging
from unittest.mock import patch, MagicMock

log = logging.getLogger("probe")

def test_emits_a_record_while_os_getpid_is_patched():
    # Exactly the production shape: a live patch on os.getpid means
    # logging.LogRecord.__init__ stores a MagicMock in record.process.
    with patch("os.getpid", MagicMock()):
        log.warning("a message")
    assert True

def test_second():
    assert True

def test_third():
    assert True
"""

_CONFTEST_WITH_HOOK = """
import pytest
from tests._xdist_report_safety import sanitize_serialized_report

@pytest.hookimpl(hookwrapper=True)
def pytest_report_to_serializable(config, report):
    outcome = yield
    data = outcome.get_result()
    safe = sanitize_serialized_report(data, nodeid=getattr(report, "nodeid", "<unknown>"))
    if safe is not data:
        outcome.force_result(safe)
"""


def _run_isolated_suite(tmp_path: Path, *, with_hook: bool) -> tuple[str, dict]:
    (tmp_path / "test_polluting.py").write_text(textwrap.dedent(_POLLUTING_SUITE))
    (tmp_path / "conftest.py").write_text(textwrap.dedent(_CONFTEST_WITH_HOOK) if with_hook else "")
    report_path = tmp_path / "report.json"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "DATABASE_URL": ""}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(tmp_path),
            "-n",
            "2",
            "-q",
            "--tb=no",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "--json-report",
            f"--json-report-file={report_path}",
            "--json-report-indent=0",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=300,
    )
    summary = json.loads(report_path.read_text())["summary"] if report_path.exists() else {}
    return proc.stdout + proc.stderr, summary


@pytest.mark.timeout(300)
def test_without_the_hook_the_session_is_silently_truncated(tmp_path):
    """The control. Without this, the test below could pass for the wrong reason."""
    output, summary = _run_isolated_suite(tmp_path, with_hook=False)
    assert "INTERNALERROR" in output, output[-3000:]
    assert summary.get("total", 0) < summary.get("collected", 0), summary
    assert not summary.get("failed"), f"and it reports no failures while doing it: {summary}"


@pytest.mark.timeout(300)
def test_with_the_hook_every_collected_item_is_reported(tmp_path):
    output, summary = _run_isolated_suite(tmp_path, with_hook=True)
    assert "INTERNALERROR" not in output, output[-3000:]
    assert summary["collected"] == summary["total"] == 3, summary
    assert summary["passed"] == 3, summary
