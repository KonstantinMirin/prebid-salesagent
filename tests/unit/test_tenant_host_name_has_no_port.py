"""``Tenant.host_name`` is a HOSTNAME, so a tenant origin's port never reaches it.

In-memory ORM instances, no database — the derivation reads one tenant column and nothing
else.
"""

from src.core.database.models import Tenant


def _host_name(virtual_host: str) -> str:
    return Tenant(tenant_id="t-port", name="Port Tenant", subdomain="ci-test", virtual_host=virtual_host).host_name


class TestHostNameDropsThePort:
    """``virtual_host`` stores the origin, port included, because the agent card publishes it.

    A reader that wants the bare name reads ``host_name``. It is the seller's host and no
    publisher's: products name the publishers of the tenant's authorized properties (#1845).
    """

    def test_port_is_dropped_from_a_virtual_host(self):
        assert _host_name("storyboard.adcp.test:8443") == "storyboard.adcp.test"

    def test_a_portless_virtual_host_is_untouched(self):
        assert _host_name("publisher.example.com") == "publisher.example.com"

    def test_an_ipv6_authority_keeps_its_whole_address(self):
        """The address survives whole. ``split(':')`` would truncate it at the first group.

        The brackets do not survive, because the derivation is ``hostname_of`` — the same
        one the tenant-resolution query compares a request's ``Host`` with. Brackets are the
        authority's spelling of an address, not part of it, and a second derivation that
        kept them would be a second answer to "what host is this tenant".
        """
        assert _host_name("[2001:db8::1]:8443") == "2001:db8::1"
        assert _host_name("[2001:db8::1]") == "2001:db8::1"
