"""BDD scenario binding for UC-010: Discover Seller Capabilities.

Uses pytest-bdd's ``scenarios()`` to auto-generate test functions from the
generated feature file. Step definitions are imported via conftest.py.

Wired set (#1594): the @T-UC-010-main-* scenarios
run a real get_adcp_capabilities through the wire transports on
CapabilitiesEnv (REST dispatches as GET — REST_METHOD support). Every other
scenario stays dormant via the UC-010 fixture catch-all xfail.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/BR-UC-010-discover-seller-capabilities.feature")
