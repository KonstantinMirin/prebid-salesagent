"""``verify_feature_error_codes.py`` must exit 2 — not 1 — when its instrument fails.

The script uses exit 1 for "non-canonical error codes found" and that code gates
``make quality``. So an *instrument* failure (the pinned enum cannot be loaded at
all) must not fall through to an uncaught traceback, which also exits 1 and would
read as "findings exist" — an empty worklist reported as a real result.

``load_enum()`` therefore catches a NAMED tuple and calls ``sys.exit(2)``.
This module pins both halves of that tuple:

- every listed type is caught and produces exit 2, and
- ``RuntimeError`` is NOT in it. The arm used to be there, attributed by comment
  to ``sdk_schema_root()``, but that function raises ``AssertionError`` for the
  SDK-layout condition (tests/helpers/sdk_schema_root.py) — nothing on
  ``load_enum()``'s call chain raises ``RuntimeError``. Re-adding the arm would
  silently re-broaden the instrument-failure net, and nothing graded that.

GH #1868
"""

from __future__ import annotations

import importlib.util

import pytest

from tests.unit._architecture_helpers import REPO_ROOT

_SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_feature_error_codes.py"


def _load_script_module():
    """Import the script by path — scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("_verify_feature_error_codes", _SCRIPT_PATH)
    assert spec and spec.loader, f"cannot load {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_script = _load_script_module()


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(AssertionError("Pinned schema not found"), id="AssertionError"),
        pytest.param(KeyError("enum"), id="KeyError"),
        pytest.param(ModuleNotFoundError("No module named 'adcp'"), id="ModuleNotFoundError"),
    ],
)
def test_instrument_failure_exits_2(monkeypatch, capsys, failure):
    """Each caught type produces the diagnostic exit code, never the findings one."""

    def _boom(_ref):
        raise failure

    monkeypatch.setattr(_script.pinned_schema, "load", _boom)

    with pytest.raises(SystemExit) as exc_info:
        _script.load_enum()

    assert exc_info.value.code == 2, (
        f"{type(failure).__name__} produced exit {exc_info.value.code}, expected 2. Exit 1 means "
        "'non-canonical codes found' and gates make quality — an instrument failure reported "
        "that way is a silent false result."
    )
    assert "pinned enum not found" in capsys.readouterr().err


def test_runtime_error_is_not_swallowed(monkeypatch):
    """RuntimeError propagates: the dead arm attributed to sdk_schema_root() is gone.

    sdk_schema_root() raises AssertionError for the missing-SDK-schema-tree
    condition the removed arm's comment described, so a RuntimeError reaching
    here would be an unrelated bug and must not be relabelled "pinned enum not
    found" and turned into exit 2.
    """

    def _boom(_ref):
        raise RuntimeError("an unrelated bug")

    monkeypatch.setattr(_script.pinned_schema, "load", _boom)

    with pytest.raises(RuntimeError, match="an unrelated bug"):
        _script.load_enum()


def test_load_enum_reads_the_pinned_enum():
    """Negative control: the happy path still returns the real vocabulary.

    Without this, every assertion above would still pass if load_enum() were
    gutted to raise unconditionally.
    """
    codes = _script.load_enum()
    assert "VALIDATION_ERROR" in codes
    assert len(codes) >= 90, f"expected the SDK's current ~92-code enum, got {len(codes)}"
