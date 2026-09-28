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

    def test_a_tenant_declaring_no_host_is_refused(self):
        """``None`` is no longer an answer: a tenant declares the host it is served at.

        This assertion is inverted from what it said before. ``None`` used to be read as a
        real state ("a print publisher has no domain"), but with Host-against-virtual_host
        one of only two ways to name a tenant (PR #2191), a host-less tenant is unreachable
        rather than domain-less — and every reader papered over it by inventing a host, which
        is what took A2A conformance from 30 checks to 0 (#1845). The same hook that folds
        case refuses the absence, so no creation path can produce one.
        """
        with pytest.raises(ValueError):
            Tenant(tenant_id="t", virtual_host=None)

    def test_a_blank_host_is_refused_too(self):
        """SQL has no opinion about ``"   "``, so the hook is what makes NOT NULL mean it."""
        with pytest.raises(ValueError):
            Tenant(tenant_id="t", virtual_host="   ")


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

    def test_a_host_less_tenant_cannot_reach_the_gate_at_all(self):
        """The gate's no-host case is now unreachable, so the refusal moved to construction.

        This used to assert ``DomainNotOwned`` for a tenant holding no host. Such a tenant
        can no longer be built, which is a stronger guarantee than the gate refusing one:
        the state the branch defended against does not exist.
        """
        with pytest.raises(ValueError):
            tenant_owns_domain(Tenant(tenant_id="t", virtual_host=None), "acme.example.com")
