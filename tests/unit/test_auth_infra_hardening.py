"""Regression tests: auth test files open source files by portable paths."""

import pathlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestNoRelativePathOpens:
    """Test files must not use relative open('src/...') paths."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "tests/unit/test_shared_header_util.py",
            "tests/unit/test_media_buy_tenant_context.py",
            "tests/unit/test_no_duplicate_auth_functions.py",
        ],
    )
    def test_no_relative_open(self, rel_path):
        """Test files must not open files with relative paths like open('src/...')."""
        source = (PROJECT_ROOT / rel_path).read_text()
        for lineno, line in enumerate(source.splitlines(), 1):
            if 'open("src/' in line or "open('src/" in line:
                pytest.fail(f"{rel_path}:{lineno} uses relative open() path: {line.strip()}")
