"""The host a request is for, read in one place.

``requested_host`` is a pure function over a header mapping, which is why it is graded
here. What it does NOT read is the point of several of these: the ``Apx-Incoming-Host``
ladder it replaced lived in eleven modules whose copies disagreed about which header
wins, and the edge now folds that header into ``Host`` before the app sees anything.

The buyer-visible half of that deletion is graded on all four transports by
``@T-TENANTID-vendor-header-ignored``; what is graded here is only the pure function.
"""

from src.core.http_utils import hostname_of, requested_host


class TestRequestedHost:
    """``requested_host`` is the ``Host``, and nothing else is a host input."""

    def test_reads_the_host(self):
        assert requested_host({"Host": "acme.example.com"}) == "acme.example.com"

    def test_reads_a_lowercase_host(self):
        assert requested_host({"host": "acme.example.com"}) == "acme.example.com"

    def test_no_host_is_none(self):
        assert requested_host({"User-Agent": "curl/8"}) is None

    def test_no_headers_at_all_is_none(self):
        assert requested_host({}) is None

    def test_the_vendor_header_is_not_a_host_input(self):
        """A request carrying only the proxy's header names no host.

        The edge folds it into ``Host``; an app-side reader would be a second spelling of
        the same fact, and the two ladders that existed disagreed about which one wins.
        """
        assert requested_host({"Apx-Incoming-Host": "acme.example.com"}) is None

    def test_the_vendor_header_does_not_override_the_host(self):
        headers = {"Host": "backend.internal", "Apx-Incoming-Host": "acme.example.com"}
        assert requested_host(headers) == "backend.internal"


class TestHostnameOf:
    """``hostname_of`` is *host* without its port."""

    def test_drops_the_port(self):
        assert hostname_of("storyboard.adcp.test:8443") == "storyboard.adcp.test"

    def test_leaves_a_portless_host_alone(self):
        assert hostname_of("storyboard.adcp.test") == "storyboard.adcp.test"

    def test_empty_host_stays_empty(self):
        assert hostname_of("") == ""
