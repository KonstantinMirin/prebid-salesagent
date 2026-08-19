"""The AdCP spec version this codebase is pinned to — one definition, shared.

This constant is read by two different suites: the unit pin-drift guard
(``tests/unit/test_adcp_spec_version.py``) and the e2e standalone schema
validation test (``tests/e2e/test_schema_validation_standalone.py``, which
asserts the loaded schema index's ``adcp_version`` agrees with the pin). It
lives here rather than in either test module because a test importing from a
sibling test module is a structural violation
(``tests/unit/test_architecture_no_cross_test_module_imports.py``) — suites are
collected independently, so such an import couples their collection order and
breaks when one suite is run alone.

See docs/adcp-spec-version.md for the bump procedure; changing this value alone
is not enough, that document lists every reference that must move with it.
"""

from __future__ import annotations

#: The AdCP spec version the pinned ``adcp`` SDK in pyproject.toml targets.
EXPECTED_SPEC_VERSION = "3.1.1"
