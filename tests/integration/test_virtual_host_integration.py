"""Integration tests for virtual host functionality.

FOUR TESTS WERE DELETED HERE, and what they were is worth recording so they are not
recreated. ``test_header_parsing_apx_incoming_host``, ``test_header_case_sensitivity``,
``test_multiple_routing_headers_priority`` and ``test_context_error_handling`` each
defined a local ``MockContext`` class, put headers into it, read them back out with a
dict access written in the test body, and asserted on what the test had just stored.
None of them imported or called anything from ``src``. ``test_multiple_routing_headers_
priority`` is the clearest case: its name and its comment claim to grade that
``Apx-Incoming-Host`` takes priority over ``Host``, and its three assertions only check
that a dict returned the three values placed in it — so it would have passed just as well
under the opposite priority, and it passed unchanged while the two real ladders in
production disagreed about exactly that question.

The header they were built around is gone from the application: the edge folds
``Apx-Incoming-Host`` into ``Host`` and drops it
(``config/nginx/nginx-multi-tenant.conf``), so the app has one host input. Which tenant a
host resolves is graded on all four transports by
``tests/bdd/features/local-tenant-identification-routes.feature``, including
``@T-TENANTID-vendor-header-ignored``, which presents the vendor header over an unserved
``Host`` and requires the refusal.

What remains is the one test here that called production.
"""

import pytest

from src.core.config_loader import get_tenant_by_virtual_host

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestVirtualHostIntegration:
    """Test virtual host integration across multiple components."""

    def test_virtual_host_function_integration(self, integration_db):
        """Test that virtual host lookup function handles non-existent domains gracefully."""
        # This is a real integration test - calls the actual function
        # with a domain that shouldn't exist
        result = get_tenant_by_virtual_host("definitely-does-not-exist.invalid")

        # Should return None for non-existent virtual hosts
        assert result is None
