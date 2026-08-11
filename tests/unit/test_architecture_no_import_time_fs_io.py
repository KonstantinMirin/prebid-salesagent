"""Guard: production modules must not touch the filesystem at import time.

Creating a directory or opening a file while a module is being imported makes
that module's importability depend on the working directory and the uid of
whoever imports it -- neither of which the module chooses, and both of which
change between a developer's shell, a container, and CI.

This is not hypothetical. ``src/core/audit_logger.py`` opened two
``logging.FileHandler``s on a CWD-relative ``logs/`` path at import time. Under
Docker two containers share ``/app`` as a bind mount while running as different
uids; whichever one created ``logs/audit.log`` first owned it at umask-derived
mode 644, and every other uid then died at pytest COLLECTION with
``PermissionError: [Errno 13] Permission denied: '/app/logs/audit.log'`` --
taking entire suites down before a single test ran, and looking like flakiness
because which container won the race varied.

Scope is ``src/`` and ``scripts/`` with NO allowlist: production code has zero
instances and must keep it that way. Deferring the work to first use is always
available -- open on demand, not on import.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    find_import_time_fs_io_violations,
    format_failure,
    iter_module_trees,
    repo_root,
)

_KNOWN_BAD_SNIPPETS = {
    "module_level_mkdir": "from pathlib import Path\nLOG_DIR = Path('logs')\nLOG_DIR.mkdir(exist_ok=True)",
    "module_level_file_handler": "import logging\nh = logging.FileHandler('logs/audit.log')",
    "module_level_makedirs": "import os\nos.makedirs('cache')",
    "module_level_open": "f = open('state.json', 'w')",
    # Control flow still executes on import -- these must not be a way around it.
    "inside_module_level_try": "import os\ntry:\n    os.makedirs('cache')\nexcept OSError:\n    pass",
    "inside_module_level_if": "import os\nif os.sep == '/':\n    os.makedirs('cache')",
    "inside_module_level_with": ("import contextlib, os\nwith contextlib.suppress(OSError):\n    os.makedirs('cache')"),
}

# Deferred execution: present in the source, but NOT run by an import.
_KNOWN_GOOD_SNIPPETS = {
    "inside_function": "import os\ndef setup():\n    os.makedirs('cache')",
    "inside_async_function": "import os\nasync def setup():\n    os.makedirs('cache')",
    "inside_method": "import os\nclass Writer:\n    def setup(self):\n        os.makedirs('cache')",
    "inside_main_guard": "import os\nif __name__ == '__main__':\n    os.makedirs('cache')",
    "no_fs_io_at_all": "from pathlib import Path\nLOG_DIR = Path('logs')\nNAME = LOG_DIR / 'audit.log'",
}


@pytest.mark.arch_guard
def test_no_import_time_filesystem_io_in_production_code() -> None:
    repo = repo_root()
    violations: list[str] = []
    for tree, rel_path in iter_module_trees([repo / "src", repo / "scripts"]):
        for lineno in find_import_time_fs_io_violations(tree):
            violations.append(f"{rel_path}:{lineno} — filesystem I/O runs at import time")

    assert not violations, format_failure(
        summary=(
            "Modules must not touch the filesystem while being imported — defer it to "
            "first use, so importing cannot fail on a path the importer never chose"
        ),
        violations=violations,
        docs_link="docs/development/structural-guards.md",
    )


@pytest.mark.arch_guard
def test_detector_catches_known_bad_snippets() -> None:
    assert_detector_catches_ast_snippets(find_import_time_fs_io_violations, snippets=_KNOWN_BAD_SNIPPETS)


@pytest.mark.arch_guard
def test_detector_ignores_deferred_filesystem_io() -> None:
    """A guard that flags every mkdir anywhere would be useless and get disabled."""
    false_positives = [
        label for label, source in _KNOWN_GOOD_SNIPPETS.items() if find_import_time_fs_io_violations(ast.parse(source))
    ]
    assert not false_positives, "Detector flagged deferred (non-import-time) filesystem I/O:\n" + "\n".join(
        f"  {label}" for label in false_positives
    )
