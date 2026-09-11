"""pytest-playwright must not be pointed at test-results/.

The plugin's ``--output`` option defaults to ``test-results`` and, at the start of
EVERY session -- UI suite or not -- it ``shutil.rmtree()``s that directory
(pytest_playwright.py, the ``_pw_artifacts_folder`` fixture). ``test-results/`` is
where run_all_tests.sh and the CI-box runner write the per-run JSON reports, which are
the baselines every failing-nodeid membership diff is made against. With the default in
force, a plain ``pytest tests/unit/<one file>`` deleted every recorded run on the
machine, and the loss was only ever noticed when a baseline named in a goal turned out
not to exist any more.

pytest.ini points the plugin at ``.playwright-artifacts`` instead. This pins that
configuration by reading the option the plugin itself reads, so the regression is a
failing unit test rather than a vanished directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_playwright_output_dir_is_not_the_reports_dir(pytestconfig: pytest.Config) -> None:
    output = Path(pytestconfig.getoption("--output"))
    reports = Path("test-results")
    assert output != reports and reports not in (output, *output.parents), (
        f"pytest-playwright --output resolves to {output}, which is (or lies under) "
        f"{reports}/ -- the plugin rmtree()s its output directory at every session start, "
        f"so this setting would delete every recorded run. Set --output in pytest.ini "
        f"addopts to a directory of its own."
    )
