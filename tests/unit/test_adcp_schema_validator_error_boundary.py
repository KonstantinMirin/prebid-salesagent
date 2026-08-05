"""AdCPSchemaValidator must translate a missing-SDK-schema-tree failure to SchemaError.

Regression for the PR #1868 review: tests/helpers/sdk_schema_root.py used to
raise a bare RuntimeError when the installed adcp SDK has no bundled schema
tree for the pinned spec version. Every other pinned-schema failure point
raises AssertionError, which AdCPSchemaValidator._resolve_pinned translates
into the public SchemaError -- "the type this module's callers branch on"
per its own docstring. AdCPSchemaValidator.__init__ calls sdk_schema_root()
directly (via _resolve_pinned, not in a bare try/except) on every
instantiation, so a caller written to the documented `except SchemaError:`
contract would not catch an SDK-layout failure one step earlier in the same
chain.

No test previously simulated a missing SDK schema tree; existing SchemaError
tests (tests/e2e/test_schema_validation_standalone.py) cover bad refs only.
"""

from __future__ import annotations

import pytest

from tests.helpers.adcp_schema_validator import AdCPSchemaValidator, SchemaError


def test_missing_sdk_schema_tree_raises_schema_error(monkeypatch):
    import adcp

    # sdk_schema_root() imports adcp at call time and derives the schema
    # directory from get_adcp_spec_version(); a nonexistent version makes
    # the directory-existence check fail, exercising the failure branch.
    monkeypatch.setattr(adcp, "get_adcp_spec_version", lambda: "0.0.0")

    # SchemaError subclasses neither RuntimeError nor AssertionError, so this
    # raises-check alone proves the boundary translation happened.
    with pytest.raises(SchemaError):
        AdCPSchemaValidator()
