"""The two pure host checks in front of the on-demand TLS gate's tenant lookup.

``GET /tls/ask`` is unauthenticated, so a host that fails ``normalize_hostname`` must be
refused before any query runs, and ``label_under`` must not read a nested name such as
``x.acme.<apex>`` as tenant ``acme`` -- with a wildcard DNS record that would turn every
name under a tenant into a certificate request. The endpoint itself, over real tenant rows,
is graded by ``tests/integration/test_tls_ask_endpoint.py``.
"""

from __future__ import annotations

import pytest

from src.core.domain_routing import label_under, normalize_hostname

APEX = "agent.example.com"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme.Agent.Example.COM", "acme.agent.example.com"),
        ("acme.agent.example.com.", "acme.agent.example.com"),
        ("  ads.publisher.example ", "ads.publisher.example"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
        ("a" * 63 + ".example", "a" * 63 + ".example"),
    ],
)
def test_hostname_is_normalized(raw, expected):
    assert normalize_hostname(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        ".",
        "a..b",
        "a b.example",
        "host.example:443",
        "evil.example/path",
        "*.example.com",
        "-lead.example",
        "trail-.example",
        "under_score.example",
        "a" * 64 + ".example",
        ("a" * 60 + ".") * 5 + "example",  # 312 characters, over the 253 limit
    ],
)
def test_malformed_hostname_is_rejected(raw):
    assert normalize_hostname(raw) is None


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (f"acme.{APEX}", "acme"),
        (APEX, None),
        (f"x.acme.{APEX}", None),
        (f"acme.{APEX}.evil.example", None),
        (f"acme{APEX}", None),
        ("random.example.org", None),
    ],
)
def test_label_under_apex(host, expected):
    assert label_under(host, APEX) == expected
