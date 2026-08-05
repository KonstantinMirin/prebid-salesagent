"""mcp_server fixture must not leak its temp log directory on a setup-failure path (SF8, salesagent-1zq3.55).

tests/integration/conftest.py::mcp_server creates output_dir via
tempfile.mkdtemp() and cleans it up with shutil.rmtree() -- but that cleanup
sits AFTER the fixture's ``yield``. Both of the fixture's own failure paths
(process died unexpectedly; server didn't come up within max_wait) raise
RuntimeError BEFORE yield, so pytest never reaches that cleanup for either
one -- the directory and its log files are left on disk in exactly the
scenario (a broken/flaky server start) this file-based logging exists to
diagnose.

These tests drive the fixture's own generator function directly
(``mcp_server.__wrapped__``, the pytest-fixture-undecorated callable) rather
than through pytest's normal fixture injection, so a forced failure can be
observed and the resulting directory state inspected without needing to
actually start a real MCP server subprocess.
"""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.integration import conftest

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _dead_process_popen(*args, **kwargs):
    """A fake subprocess.Popen whose process is already dead (poll() != None)."""
    fake_process = MagicMock()
    fake_process.poll.return_value = 1  # Non-None: process exited immediately
    return fake_process


def _alive_process_popen(*args, **kwargs):
    """A fake subprocess.Popen whose process never dies but never opens its port either."""
    fake_process = MagicMock()
    fake_process.poll.return_value = None  # Always "still running"
    return fake_process


class TestMcpServerFixtureCleanup:
    """Neither setup-failure path may leave a mcp-server-* temp dir behind."""

    def _leaked_dirs(self) -> list[Path]:
        return list(Path("/tmp").glob("mcp-server-*"))

    def test_no_leak_when_process_dies_before_yield(self, integration_db):
        """Process-died path: subprocess.Popen.poll() reports a dead process
        on the very first readiness check, so the fixture raises before
        yield without any 60s wait."""
        gen = conftest.mcp_server.__wrapped__(integration_db)
        try:
            with patch("subprocess.Popen", side_effect=_dead_process_popen):
                with pytest.raises(RuntimeError, match="MCP server process died unexpectedly"):
                    next(gen)

            leaked = self._leaked_dirs()
            assert not leaked, f"mcp_server fixture leaked temp dir(s) on the process-died path: {leaked}"
        finally:
            for d in self._leaked_dirs():
                shutil.rmtree(d, ignore_errors=True)

    def test_no_leak_when_server_never_becomes_ready(self, integration_db):
        """Timeout path: the process stays "alive" (poll() -> None) but never
        opens its port, and time.time() is patched to jump straight past
        max_wait so the test doesn't actually sleep 60s."""
        gen = conftest.mcp_server.__wrapped__(integration_db)
        try:
            with (
                patch("subprocess.Popen", side_effect=_alive_process_popen),
                patch("time.time", side_effect=itertools.chain([0], itertools.repeat(999_999))),
            ):
                with pytest.raises(RuntimeError, match="MCP server failed to start"):
                    next(gen)

            leaked = self._leaked_dirs()
            assert not leaked, f"mcp_server fixture leaked temp dir(s) on the startup-timeout path: {leaked}"
        finally:
            for d in self._leaked_dirs():
                shutil.rmtree(d, ignore_errors=True)
