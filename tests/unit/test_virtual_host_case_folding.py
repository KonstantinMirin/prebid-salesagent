"""``virtual_host`` is all lowercase, and the two halves of that rule with no DB in them.

A ``Host`` names a DNS name and DNS is case-insensitive (RFC 7230 §5.4), so
``Probe-Case.AdCP.test`` and ``probe-case.adcp.test`` are ONE host. The column is
``Text`` and SQL comparison is not case-folding, so a row stored with a capital was
unroutable on every reader that answers "which tenant serves this request" — the tenant
was reachable only through the ``x-adcp-tenant`` literal-id path (PR #2191).

The fix is the rule end to end: folded on write, folded again wherever a host is compared
or published. Graded here are the two halves that need no database — the column's own
validator, which fires on assignment, and the domain-ownership gate, which is a pure
comparison. The three READERS (the resolver, the landing page, the agent card) each need
a committed row and are graded together in
``tests/integration/test_virtual_host_integration.py``.
"""

import pytest

from src.core.database.models import Tenant
from src.services.approximated_client import DomainNotOwned, tenant_owns_domain

pytestmark = pytest.mark.unit

MIXED = "Probe-Case.AdCP.test"


class TestTheColumnFoldsOnAssignment:
    """``Tenant.virtual_host`` holds no uppercase, whatever it is handed."""

    def test_an_uppercase_host_is_stored_folded(self):
        assert Tenant(tenant_id="t", virtual_host=MIXED).virtual_host == MIXED.lower()

    def test_a_later_assignment_folds_too(self):
        """The admin settings form assigns after construction — the same hook must fire."""
        tenant = Tenant(tenant_id="t", virtual_host="already.lower.test")
        tenant.virtual_host = MIXED.upper()

        assert tenant.virtual_host == MIXED.lower()

    def test_a_tenant_declaring_no_host_keeps_none(self):
        """``None`` is a real answer — a tenant without a domain is a real seller."""
        assert Tenant(tenant_id="t", virtual_host=None).virtual_host is None


class TestTheDomainOwnershipGateFoldsBothSides:
    """The Approximated gate proves a host, so it compares hosts case-insensitively."""

    def test_a_differently_cased_domain_is_still_owned(self):
        tenant = Tenant(tenant_id="t", virtual_host="acme.example.com")

        assert tenant_owns_domain(tenant, "Acme.Example.COM").domain == "Acme.Example.COM"

    def test_a_different_domain_is_still_refused(self):
        """Folding widens the comparison to case and to nothing else."""
        tenant = Tenant(tenant_id="t", virtual_host="acme.example.com")

        with pytest.raises(DomainNotOwned):
            tenant_owns_domain(tenant, "other.example.com")

    def test_a_tenant_with_no_host_owns_nothing(self):
        with pytest.raises(DomainNotOwned):
            tenant_owns_domain(Tenant(tenant_id="t", virtual_host=None), "acme.example.com")
