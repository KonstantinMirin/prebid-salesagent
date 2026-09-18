"""The host a request names, read in one place.

``Apx-Incoming-Host`` (the Approximated proxy's spelling of the host the client asked
for) and ``Host`` were read by a ladder copied into eleven modules, each with its own
case handling. These are the pure functions that ladder collapsed to; they take a header
mapping and return a string, so they are graded here.
"""

from src.core.http_utils import hostname_of, proxied_host, requested_host


class TestProxiedHost:
    """``proxied_host`` is the only reader of the Approximated header's name."""

    def test_reads_the_canonical_spelling(self):
        assert proxied_host({"Apx-Incoming-Host": "acme.example.com"}) == "acme.example.com"

    def test_reads_a_lowercase_spelling(self):
        assert proxied_host({"apx-incoming-host": "acme.example.com"}) == "acme.example.com"

    def test_reads_a_shouted_spelling(self):
        assert proxied_host({"APX-INCOMING-HOST": "acme.example.com"}) == "acme.example.com"

    def test_absent_header_is_none(self):
        assert proxied_host({"Host": "acme.example.com"}) is None

    def test_no_headers_at_all_is_none(self):
        assert proxied_host({}) is None


class TestRequestedHost:
    """``requested_host`` is the proxy's spelling, else ``Host``."""

    def test_proxy_header_wins_over_host(self):
        headers = {"Host": "backend.internal", "Apx-Incoming-Host": "acme.example.com"}
        assert requested_host(headers) == "acme.example.com"

    def test_falls_back_to_host(self):
        assert requested_host({"Host": "acme.example.com"}) == "acme.example.com"

    def test_falls_back_to_a_lowercase_host(self):
        assert requested_host({"host": "acme.example.com"}) == "acme.example.com"

    def test_neither_header_is_none(self):
        assert requested_host({"User-Agent": "curl/8"}) is None


class TestHostnameOf:
    """``hostname_of`` is *host* without its port."""

    def test_drops_the_port(self):
        assert hostname_of("storyboard.adcp.test:8443") == "storyboard.adcp.test"

    def test_leaves_a_portless_host_alone(self):
        assert hostname_of("storyboard.adcp.test") == "storyboard.adcp.test"

    def test_empty_host_stays_empty(self):
        assert hostname_of("") == ""
