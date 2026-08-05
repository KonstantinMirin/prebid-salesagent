"""Vendor and operator egress, driven at a REAL local origin — the retry-drift gate.

salesagent-gstl migrates the ten remaining operator-configured call sites onto
``src/core/security/outbound_http.py``. The seam decides address policy, TLS
policy, redirect refusal, the response-size cap, the attempt count and the
backoff schedule, and it grades all six exactly once, in
``tests/integration/test_outbound_http.py``. Re-asserting any of them here would
be the duplication the seam exists to delete.

What this file grades is the one property the seam CANNOT decide for a call
site: **how many times the site is willing to hit the origin**. The seam takes
``max_attempts`` as an argument, so a migration that passes the wrong number —
or that leaves a second attempt-count wrapped around the method, where neither
the ``ruff-egress.toml`` import bans nor ``test_architecture_no_call_site_backoff``
can see it — turns one failed campaign create into three. Campaign, flight and
creative creation are POSTs; they are not idempotent; a buyer pays for the
duplicates.

So every case here points a real production method at a real HTTP server that
really ran, programs it to fail, and asserts on ``local_origin.hits`` — the
count of requests the server actually received. A transport mock's
``call_count`` cannot make that claim: it counts calls the test itself
arranged, on a code path the client never walked.

The private-range egress escape hatch is opened explicitly (``allow_local_origin``)
because a local origin is loopback, which the seam refuses by default and
rightly so; it is a no-op before the migration (``requests`` has no address
policy) and load-bearing after it, so the cases read identically on both sides
of the change. The origin itself is served over real TLS (``local_origin_tls``,
salesagent-e6h0) since the seam requires https unconditionally now — there is
no scheme hatch left to open.

Two of the ten sites have no origin-driven case here, and that is a finding
rather than a gap. They are stated as failing assertions rather than skip
markers, because a skip claims a test exists:

* ``src/admin/blueprints/settings.py`` (4 calls) hardcodes
  ``https://cloud.approximated.app/...`` as a string literal at each call site.
* ``src/admin/blueprints/auth.py`` (1 call) hardcodes
  ``https://oauth2.googleapis.com/token``.

Neither can be pointed at a local origin without changing ``src/``, so the
ticket's own gates 2 and 3 ("succeeds against a local origin standing in for
Google") are unreachable until the implementer hoists those hosts to a
module-level constant. The two cases at the bottom of this file assert exactly
that affordance exists, and fail today with a message naming it. They are the
red that unblocks the gate, not a substitute for it.
"""

from __future__ import annotations

import gzip
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import requests

from src.core.exceptions import AdCPError
from src.core.schemas import Principal
from src.core.security.outbound_http import OutboundError
from tests.harness._base import IntegrationEnv
from tests.helpers.local_http_origin import LocalOrigin

# Reused rather than restated: which escape hatches a case opens is one decision
# with one home, and the backoff knob that keeps a retry case fast is the seam
# suite's own helper.
from tests.integration.property_list_helpers import allow_local_origin
from tests.integration.test_outbound_http import fast_backoff

pytestmark = [pytest.mark.integration]

_TODAY = datetime(2026, 7, 29, tzinfo=UTC)

# The exception TYPE a vendor call raises is exactly what the migration changes:
# ``requests.exceptions.RequestException`` today, an ``OutboundError`` or a mapped
# ``AdCPError`` once the site routes through the seam. This file grades attempt
# counts, so it names all three and leaves the taxonomy to be graded where it
# belongs — ``tests/integration/test_outbound_http.py`` for the seam's own
# classes, the adapter's error tests for the mapping.
_VENDOR_FAILURE = (requests.exceptions.RequestException, OutboundError, AdCPError)


class _BareEnv(IntegrationEnv):
    """Binds the factory session to the real database; patches nothing.

    The only egress in this file goes to a server that really ran, so an env
    that patched anything would be patching the thing under test.
    """

    EXTERNAL_PATCHES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Adapter construction — real schema objects, no Mock principals.
# ---------------------------------------------------------------------------


def _principal(adapter: str, mappings: dict[str, Any] | None = None) -> Principal:
    """A real ``Principal`` carrying an advertiser id for *adapter*."""
    return Principal(
        principal_id="test_principal",
        name="Test Buyer",
        platform_mappings=mappings or {adapter: {"advertiser_id": "123"}},
    )


def _kevel(origin: LocalOrigin):
    """A live-mode Kevel adapter whose API base is the local origin.

    ``base_url`` is assigned after construction because ``Kevel.__init__``
    hardcodes ``https://api.kevel.co/v1`` and ignores ``config["base_url"]`` —
    a fact worth knowing before the migration touches it.
    """
    from src.adapters.kevel import Kevel

    adapter = Kevel(
        config={"network_id": "456", "api_key": "test-key"},
        principal=_principal("kevel"),
        dry_run=False,
        tenant_id="test_tenant",
    )
    adapter.base_url = origin.base_url
    return adapter


def _triton(origin: LocalOrigin):
    from src.adapters.triton_digital import TritonDigital

    return TritonDigital(
        config={"base_url": origin.base_url, "auth_token": "test-token"},
        principal=_principal("triton"),
        dry_run=False,
        tenant_id="test_tenant",
    )


def _xandr(origin: LocalOrigin):
    """A concrete Xandr adapter pointed at the local origin.

    ``XandrAdapter`` does not implement four of ``AdServerAdapter``'s abstract
    methods, so it cannot be instantiated as shipped. The subclass supplies the
    missing names and nothing else — none of them is on the path under test.
    """
    from src.adapters.xandr import XandrAdapter

    class _ConcreteXandr(XandrAdapter):
        def add_creative_assets(self, *args, **kwargs): ...

        def associate_creatives(self, *args, **kwargs): ...

        def check_media_buy_status(self, *args, **kwargs): ...

        def update_media_buy_performance_index(self, *args, **kwargs): ...

    return _ConcreteXandr(
        config={
            "api_endpoint": origin.base_url,
            "username": "user",
            "password": "pass",
            "member_id": "789",
        },
        principal=_principal("xandr", {"xandr": {"advertiser_id": "123"}}),
        tenant_id="test_tenant",
    )


def _mock_ad_server(origin: LocalOrigin):
    """A mock adapter configured to post its HITL completion webhook at *origin*."""
    from src.adapters.mock_ad_server import MockAdServer

    principal = Principal(
        principal_id="test_principal",
        name="Test Buyer",
        platform_mappings={
            "mock": {
                "advertiser_id": "123",
                "hitl_config": {
                    "enabled": True,
                    "mode": "async",
                    "async_settings": {"webhook_url": origin.base_url, "webhook_on_complete": True},
                },
            }
        },
    )
    return MockAdServer(config={}, principal=principal, dry_run=False, tenant_id="test_tenant")


def _broadstreet(origin: LocalOrigin):
    from src.adapters.broadstreet.client import BroadstreetClient

    return BroadstreetClient(access_token="test-token", network_id="456", base_url=origin.base_url)


# ---------------------------------------------------------------------------
# 1. Retry drift — one failed vendor call must cost the origin exactly ONE hit.
# ---------------------------------------------------------------------------


def test_xandr_authenticate_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """``XandrAdapter._authenticate`` must hit a 500 origin once, not three times.

    This is the headline case. ``_authenticate`` is wrapped in ``@api_retry``
    (``src/core/retry_utils.py``: ``max_attempts=3``), so the site owns an
    attempt count of its own — one that survives the migration untouched and
    that no structural guard can see, because ``no_call_site_backoff`` only
    matches an ``ast.Pow`` and ``retry_utils`` compounds with ``*=``.
    """
    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _xandr(local_origin_tls)

    with pytest.raises(_VENDOR_FAILURE):
        adapter._authenticate()

    assert local_origin_tls.hits == 1


def test_xandr_make_request_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """``XandrAdapter._make_request`` must hit a 500 origin once.

    The token is pre-seeded so ``_authenticate`` returns early and every hit
    counted here belongs to the request itself — otherwise the two decorated
    methods nest and the number says nothing about either one.
    """
    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _xandr(local_origin_tls)
    adapter.token = "seeded-token"
    adapter.token_expiry = datetime.now(UTC) + timedelta(hours=1)

    with pytest.raises(_VENDOR_FAILURE):
        adapter._make_request("POST", "/campaign", {"name": "x"})

    assert local_origin_tls.hits == 1


def test_xandr_make_request_compounds_its_retries_with_authenticate(local_origin_tls, monkeypatch):
    """A Xandr call on an expired token must still cost the origin ONE hit.

    ``_make_request`` calls ``_authenticate`` and both carry ``@api_retry``, so
    the two attempt counts multiply rather than add. This is the worst case a
    buyer can hit — the token expires, the vendor is down — and it is the one
    the ``max_attempts=1`` the migration passes to the seam would describe
    least accurately.
    """
    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _xandr(local_origin_tls)

    with pytest.raises(_VENDOR_FAILURE):
        adapter._make_request("POST", "/campaign", {"name": "x"})

    assert local_origin_tls.hits == 1


def test_kevel_update_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """A failed Kevel campaign pause costs one hit and surfaces as a transient service failure.

    Asserts the WIRE contract (SERVICE_UNAVAILABLE / transient), not the Python
    class. A 5xx now arrives as ``OutboundDeliveryFailed``, which already IS an
    ``AdCPServiceUnavailableError`` with exactly the code and recovery
    ``AdCPAdapterError`` carried — the mapper re-raises it unchanged rather than
    rewrapping, which is the duplication this epic removes. Pinning the class here
    would grade an implementation detail the migration deliberately changes at
    every site.
    """
    from src.core.exceptions import AdCPError

    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _kevel(local_origin_tls)

    with pytest.raises(AdCPError) as exc_info:
        adapter.update_media_buy(
            media_buy_id="kevel_999",
            action="pause_media_buy",
            package_id=None,
            budget=None,
            today=_TODAY,
        )

    assert exc_info.value.error_code == "SERVICE_UNAVAILABLE"
    assert exc_info.value.recovery == "transient"
    assert local_origin_tls.hits == 1


def test_triton_status_check_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """A failed Triton status check costs one hit and degrades to ``unknown``.

    The degradation is asserted alongside the count because it is the arm the
    migration has to preserve: ``except requests.exceptions.RequestException``
    narrows to ``except OutboundError``, and a miss there turns a soft
    "unknown" into a raised error on a read path.
    """
    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _triton(local_origin_tls)
    response = adapter.check_media_buy_status(media_buy_id="triton_999", today=_TODAY)

    assert response.status == "unknown"
    assert local_origin_tls.hits == 1


def test_broadstreet_request_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """A 500 from Broadstreet costs one hit and raises ``BroadstreetAPIError``."""
    from src.adapters.broadstreet.client import BroadstreetAPIError

    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    client = _broadstreet(local_origin_tls)

    with pytest.raises(BroadstreetAPIError) as exc_info:
        client.get("/networks")

    assert exc_info.value.status_code == 500
    assert local_origin_tls.hits == 1


def test_mock_ad_server_webhook_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """The HITL completion webhook costs one hit and never raises."""
    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b'{"error": "boom"}')

    adapter = _mock_ad_server(local_origin_tls)
    adapter._send_completion_webhook("step_1", approved=True)

    assert local_origin_tls.hits == 1


def test_gam_report_download_does_not_retry_a_failing_origin(local_origin_tls, monkeypatch):
    """A failed GAM report download costs one hit.

    The GAM SOAP client is a plain fake, not a transport mock: it stands in for
    the external ad server that hands back a download URL, which is the only
    way this call site can be reached at all. The HTTP that follows is real.

    ``ReportingConfig.ALLOWED_DOMAINS`` is widened for the same reason
    ``allow_local_origin`` opens the seam's hatches — the check is a
    Google-provenance guard on the URL, and a loopback origin is not Google.
    """
    from src.adapters import gam_reporting_service as grs

    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    monkeypatch.setattr(grs.ReportingConfig, "ALLOWED_DOMAINS", ["127.0.0.1"])
    local_origin_tls.respond_with(500, body=b"boom")

    service = _gam_reporting_service(local_origin_tls)

    # ``_run_report`` wraps every failure in a bare ``Exception`` of its own, so
    # the message is the only thing there is to assert on. It is written in
    # ``gam_reporting_service`` and the migration does not touch it.
    with pytest.raises(Exception, match="Error running GAM report"):
        service._run_report({"reportQuery": {}})

    assert local_origin_tls.hits == 1


def test_base_workflow_slack_notification_reaches_the_origin_once(local_origin_tls, monkeypatch, integration_db):
    """The workflow Slack notification must reach its webhook exactly once.

    Exactly once, not zero: the count grades both halves of the obligation, and
    a site that never fires cannot have its attempt count migrated correctly
    either.
    """
    from src.adapters.base_workflow import BaseWorkflowManager
    from src.core.config_loader import current_tenant

    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(200, body=b"ok")

    # The tenant context is a ContextVar, so it is reset explicitly rather than
    # left behind for whichever test this worker runs next.
    token = current_tenant.set(
        {
            "tenant_id": "test_tenant",
            "name": "Test Tenant",
            "slack_webhook_url": local_origin_tls.base_url,
            "slack": {"webhook_url": local_origin_tls.base_url},
        }
    )
    try:
        manager = BaseWorkflowManager(tenant_id="test_tenant")
        manager._send_workflow_notification("step_1", {"platform": "mock", "automation_mode": "manual"})
    finally:
        current_tenant.reset(token)

    assert local_origin_tls.hits == 1


def test_admin_slack_test_message_does_not_retry_a_failing_origin(
    local_origin_tls, monkeypatch, authenticated_admin_session, integration_db
):
    """``POST /tenant/<id>/test_slack`` costs the webhook one hit on a 500."""
    from tests.factories import TenantFactory

    allow_local_origin(monkeypatch)
    fast_backoff(monkeypatch)
    local_origin_tls.respond_with(500, body=b"boom")

    with _BareEnv():
        TenantFactory(tenant_id="slack_test_tenant", slack_webhook_url=local_origin_tls.base_url)

    response = authenticated_admin_session.post("/tenant/slack_test_tenant/test_slack")

    assert response.get_json()["success"] is False
    assert local_origin_tls.hits == 1


# ---------------------------------------------------------------------------
# 2. Happy paths — the vendor shapes the adapters actually parse.
# ---------------------------------------------------------------------------


def test_broadstreet_get_returns_the_parsed_body(local_origin_tls, monkeypatch):
    allow_local_origin(monkeypatch)
    local_origin_tls.respond_with(200, body=b'{"networks": [{"id": 456}]}')

    client = _broadstreet(local_origin_tls)

    assert client.get("/networks") == {"networks": [{"id": 456}]}
    assert local_origin_tls.hits == 1


def test_triton_status_check_reads_an_active_campaign(local_origin_tls, monkeypatch):
    allow_local_origin(monkeypatch)
    local_origin_tls.respond_with(200, body=b'{"active": true, "endDate": "2030-01-01T00:00:00+00:00"}')

    adapter = _triton(local_origin_tls)
    response = adapter.check_media_buy_status(media_buy_id="triton_999", today=_TODAY)

    assert response.status == "active"
    assert local_origin_tls.hits == 1


def test_kevel_pause_succeeds_against_a_local_origin(local_origin_tls, monkeypatch):
    allow_local_origin(monkeypatch)
    local_origin_tls.respond_with(200, body=b'{"Id": 999, "IsActive": false}')

    adapter = _kevel(local_origin_tls)
    response = adapter.update_media_buy(
        media_buy_id="kevel_999",
        action="pause_media_buy",
        package_id=None,
        budget=None,
        today=_TODAY,
    )

    assert response.media_buy_id == "kevel_999"
    assert local_origin_tls.hits == 1


def test_xandr_make_request_returns_the_parsed_body(local_origin_tls, monkeypatch):
    allow_local_origin(monkeypatch)
    local_origin_tls.respond_with(200, body=b'{"response": {"status": "OK", "id": 42}}')

    adapter = _xandr(local_origin_tls)
    adapter.token = "seeded-token"
    adapter.token_expiry = datetime.now(UTC) + timedelta(hours=1)

    assert adapter._make_request("GET", "/campaign") == {"response": {"status": "OK", "id": 42}}
    assert local_origin_tls.hits == 1


def test_mock_ad_server_webhook_posts_the_completion_payload(local_origin_tls, monkeypatch):
    allow_local_origin(monkeypatch)
    local_origin_tls.respond_with(200, body=b"ok")

    adapter = _mock_ad_server(local_origin_tls)
    adapter._send_completion_webhook("step_1", approved=True)

    payload = local_origin_tls.last_request.json()
    assert payload["event"] == "task_completed"
    assert payload["step_id"] == "step_1"
    assert payload["status"] == "completed"
    assert local_origin_tls.hits == 1


def test_gam_report_download_parses_the_gzipped_csv(local_origin_tls, monkeypatch):
    from src.adapters import gam_reporting_service as grs

    allow_local_origin(monkeypatch)
    monkeypatch.setattr(grs.ReportingConfig, "ALLOWED_DOMAINS", ["127.0.0.1"])

    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(b"Dimension.DATE,Column.AD_SERVER_IMPRESSIONS\n2026-07-29,100\n")
    local_origin_tls.respond_with(200, body=buffer.getvalue(), content_type="application/octet-stream")

    service = _gam_reporting_service(local_origin_tls)
    rows = service._run_report({"reportQuery": {}})

    assert rows == [{"Dimension.DATE": "2026-07-29", "Column.AD_SERVER_IMPRESSIONS": "100"}]
    assert local_origin_tls.hits == 1


# ---------------------------------------------------------------------------
# 3. The two hardcoded-host sites — the affordance their gates need.
# ---------------------------------------------------------------------------


def test_approximated_base_url_is_injectable():
    """``settings.py``'s four Approximated calls must not hardcode the host.

    Gate 2 of the ticket ("adapter happy paths against a local origin") cannot
    be written for these four while ``https://cloud.approximated.app`` is a
    string literal repeated at each call site: a test has no seam to point
    anywhere. Hoisting the base to one module-level constant is what makes the
    gate writable, and it deletes three copies of a URL at the same time.
    """
    from src.admin.blueprints import settings

    base = getattr(settings, "APPROXIMATED_BASE_URL", None)
    assert base is not None, (
        "src/admin/blueprints/settings.py hardcodes https://cloud.approximated.app at "
        "each of its four call sites, so none of them can be driven at a local "
        "origin. Hoist the host to a module-level APPROXIMATED_BASE_URL."
    )


def test_google_token_url_is_injectable():
    """``auth.py``'s OAuth token exchange must not hardcode Google's host.

    Gate 3 asks for the token POST to succeed against a local origin standing
    in for Google. That is unreachable while the URL is a literal inside the
    view function.
    """
    from src.admin.blueprints import auth

    token_url = getattr(auth, "GOOGLE_TOKEN_URL", None)
    assert token_url is not None, (
        "src/admin/blueprints/auth.py hardcodes https://oauth2.googleapis.com/token "
        "inside gam_callback, so the token exchange cannot be driven at a local "
        "origin. Hoist it to a module-level GOOGLE_TOKEN_URL."
    )


# ---------------------------------------------------------------------------
# GAM SOAP stand-in — a fake external ad server, not a transport mock.
# ---------------------------------------------------------------------------


class _FakeReportService:
    """The four ``ReportService`` methods ``_run_report`` calls, and nothing else."""

    def __init__(self, download_url: str) -> None:
        self._download_url = download_url

    def runReportJob(self, report_job):  # noqa: N802 - GAM SOAP name
        return {"id": "report_job_1"}

    def getReportJobStatus(self, report_job_id):  # noqa: N802 - GAM SOAP name
        return "COMPLETED"

    def getReportDownloadURL(self, report_job_id, export_format):  # noqa: N802 - GAM SOAP name
        return self._download_url


class _FakeGAMClient:
    def __init__(self, download_url: str) -> None:
        self._report_service = _FakeReportService(download_url)

    def GetService(self, name):  # noqa: N802 - GAM SDK name
        return self._report_service


def _gam_reporting_service(origin: LocalOrigin):
    """A reporting service whose report downloads land on *origin*.

    ``network_timezone`` is passed so construction never reaches
    ``NetworkService`` — the timezone lookup is not on the path under test.
    """
    from src.adapters.gam_reporting_service import GAMReportingService

    return GAMReportingService(
        _FakeGAMClient(f"{origin.base_url}/report.csv.gz"),
        network_timezone="America/New_York",
    )
