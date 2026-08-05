"""Ingest-time egress policy, graded through the real admin endpoints.

Admin write handlers accept URLs that are STORED now and fetched later, so the
refusal has to happen at ingest. These cases drive the actual Flask routes —
``POST /tenant/<id>/signals-agents/add`` and the tenant-management JSON API —
against a real database, because the obligation is not "``validate_url`` says
no" (``tests/integration/test_outbound_http.py`` grades that already) but "the
handler asks, and acts on the answer". Deleting the call in either handler has
to turn these red; that is the whole point of going through the route rather
than calling a helper.

Nothing here is mocked: no patched resolver, no substituted validator. The
refusals are produced by the live ``adcp.signing`` validator against real
addresses — ``169.254.169.254`` genuinely is a cloud-metadata address — so a
mock could only restate the assertion instead of grading it. Both escape
hatches are set explicitly on every case via the shared ``set_flags`` helper,
so a case never depends on ambient environment.

Two behaviour changes over the validator these handlers used to call, both
asserted below:

* the operator-facing message is opaque — the real reason (which names the
  resolved IP and distinguishes "cannot resolve" from "reserved range") reaches
  the operator through the logs instead of the response;
* plain ``http://`` is now REJECTED, where the old validator allowed it.

Spec grounding: AdCP 3.1.1, ``building/by-layer/L1/security.mdx``, "Webhook URL
validation (SSRF)" — point 2 (reject reserved ranges), point 1 (reject
non-HTTPS) and point 6 (do not echo fetch errors back to the party that
supplied the URL). Conformance storyboard: ungraded — an L1 security
obligation, not a wire contract.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import select

from src.core.database.models import CreativeAgent, PushNotificationConfig, SignalsAgent, Tenant
from tests.factories import PrincipalFactory
from tests.integration.test_outbound_http import set_flags

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# A cloud-metadata address: refused by address policy whatever the hatches say,
# and a literal IP so no DNS answer can make the case flaky.
METADATA_URL = "https://169.254.169.254/agent"

# A public host over plain http. Only the scheme rule can refuse this, which is
# what makes it a test of behaviour change (b) rather than of address policy —
# and the scheme is checked before any resolution, so it needs no network.
INSECURE_PUBLIC_URL = "http://signals.example.com/agent"

# The reason the operator must NOT be handed back. Any of these appearing in a
# response body would be the leak point 6 forbids.
LEAKED_FRAGMENTS = ("169.254.169.254", "reserved", "resolve", "metadata")

TENANT_ID = "ingest_url_policy"
API_KEY = "sk-ingest-url-policy-test"


@pytest.fixture
def seeded_tenant(integration_db):
    """A committed tenant for the admin routes to write against.

    ``IntegrationEnv`` is what binds the factories to a session; the factory
    commits, so the Flask handler's own session sees the row.
    """
    from tests.factories import TenantFactory
    from tests.harness._base import IntegrationEnv

    with IntegrationEnv() as env:
        TenantFactory(tenant_id=TENANT_ID, name="Ingest URL Policy", subdomain="ingesturlpolicy")
        yield env


PRINCIPAL_ID = "ingest_url_policy_principal"


@pytest.fixture
def seeded_principal(seeded_tenant):
    """A committed principal under ``seeded_tenant``, for webhook registration."""
    session = seeded_tenant.get_session()
    tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
    PrincipalFactory(tenant=tenant, principal_id=PRINCIPAL_ID)
    return seeded_tenant


@pytest.fixture
def management_api_client(seeded_tenant, monkeypatch):
    """Client for the tenant-management JSON API, authenticated by env-var key.

    ``get_api_key_from_config`` prefers the environment variable over the DB
    row, so the key needs no fixture-time write.
    """
    from flask import Flask

    from src.admin.tenant_management_api import tenant_management_api

    monkeypatch.setenv("TENANT_MANAGEMENT_API_KEY", API_KEY)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tenant_management_api)
    return app.test_client()


def flashes(client) -> list[tuple[str, str]]:
    """The (category, message) pairs queued for the next rendered page.

    Read from the session rather than from rendered HTML: the flash is the
    thing the handler produced, and the template is not under test here.
    """
    with client.session_transaction() as session:
        return list(session.get("_flashes", []))


def signals_agents_for(env) -> list[SignalsAgent]:
    """Every signals agent row for the test tenant, read fresh.

    ``rollback()`` ends whatever transaction the factory session is holding, so
    the following SELECT sees what the handler's separate session committed
    (or, for a refusal, did not).
    """
    session = env.get_session()
    session.rollback()
    return list(session.scalars(select(SignalsAgent).filter_by(tenant_id=TENANT_ID)).all())


def post_signals_agent(client, url: str):
    """POST the signals-agent add form with *url* as the agent URL."""
    return client.post(
        f"/tenant/{TENANT_ID}/signals-agents/add",
        data={"agent_url": url, "name": "Ingest Policy Agent", "enabled": "on", "timeout": "30"},
        follow_redirects=False,
    )


ADMITTED_URL = "https://127.0.0.1:9999/agent"


def create_agent_through_the_add_form(client, env, monkeypatch) -> SignalsAgent:
    """Seed one signals agent by driving the real add endpoint.

    There is no ``SignalsAgentFactory``, and hand-writing the row would test a
    row this application never wrote. Both hatches are open for the duration of
    the seed only — every case that follows re-sets them for what it is
    actually grading.
    """
    set_flags(monkeypatch, private=True)
    response = post_signals_agent(client, ADMITTED_URL)
    assert response.status_code == 302, "seeding the agent through the add form failed"
    agents = signals_agents_for(env)
    assert len(agents) == 1, f"expected exactly one seeded agent, got {agents}"
    return agents[0]


# ---------------------------------------------------------------------------
# The blueprint form shape: flash + redirect back to the form, nothing stored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [METADATA_URL, INSECURE_PUBLIC_URL])
def test_signals_agent_add_refuses_and_stores_nothing(
    url, authenticated_admin_client, seeded_tenant, monkeypatch, caplog
):
    """A refused agent URL redirects back to the form, flashes, and creates no row.

    The row assertion is what makes this more than a status-code test: a
    handler that flashed and then fell through to ``session.add`` would pass on
    the redirect alone. ``INSECURE_PUBLIC_URL`` is the parametrised case for
    behaviour change (b) — plain http used to be accepted here.
    """
    set_flags(monkeypatch)
    caplog.set_level(logging.WARNING)

    response = post_signals_agent(authenticated_admin_client, url)

    assert response.status_code == 302
    assert "/signals-agents/add" in response.headers["Location"]
    assert flashes(authenticated_admin_client) == [("error", "Agent URL is not allowed by outbound egress policy.")]
    assert signals_agents_for(seeded_tenant) == []


def test_signals_agent_add_accepts_a_url_egress_policy_admits(authenticated_admin_client, seeded_tenant, monkeypatch):
    """A URL the policy admits is stored — the check refuses, it does not reject everything.

    Without this the refusal cases above would also pass against a handler that
    rejected every URL unconditionally. Both hatches are open so the case can
    use a loopback address and stay entirely off the network: ``validate_url``
    connects to nothing, so no origin has to be listening on this port.
    """
    set_flags(monkeypatch, private=True)

    response = post_signals_agent(authenticated_admin_client, ADMITTED_URL)

    assert response.status_code == 302
    assert "/signals-agents/add" not in response.headers["Location"]
    stored = signals_agents_for(seeded_tenant)
    assert [agent.agent_url for agent in stored] == [ADMITTED_URL]


@pytest.mark.parametrize("url", [METADATA_URL, INSECURE_PUBLIC_URL])
def test_signals_agent_edit_refuses_and_leaves_the_stored_url_alone(
    url, authenticated_admin_client, seeded_tenant, monkeypatch
):
    """Editing an admitted URL into a refused one is rejected and does not persist.

    The edit handler assigns every form value onto the loaded ORM object BEFORE
    validating, so the object in the session already holds the refused URL by
    the time the check runs. What keeps that out of the database is returning
    without committing — ``get_db_session`` closes rather than commits. Reading
    the column back is the only assertion that can tell those two apart; the
    302 alone cannot.
    """
    agent = create_agent_through_the_add_form(authenticated_admin_client, seeded_tenant, monkeypatch)
    set_flags(monkeypatch)

    response = authenticated_admin_client.post(
        f"/tenant/{TENANT_ID}/signals-agents/{agent.id}/edit",
        data={"agent_url": url, "name": "Ingest Policy Agent", "enabled": "on", "timeout": "30"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/edit" in response.headers["Location"]
    assert [stored.agent_url for stored in signals_agents_for(seeded_tenant)] == [ADMITTED_URL]


def test_signals_agent_test_connection_refuses_a_stored_url_without_connecting(
    authenticated_admin_client, seeded_tenant, monkeypatch
):
    """A stored URL is graded again on the way out, in the endpoint's own JSON envelope.

    This is the third response shape: ``{"success": false, "error": ...}`` at
    400, not the bare ``{"error": ...}`` the tenant-management API returns. A
    row written while the hatches were open must not become an outbound request
    once they are closed — which is exactly why the check is repeated at send
    time rather than trusted from ingest.
    """
    agent = create_agent_through_the_add_form(authenticated_admin_client, seeded_tenant, monkeypatch)
    set_flags(monkeypatch)

    response = authenticated_admin_client.post(
        f"/tenant/{TENANT_ID}/signals-agents/{agent.id}/test",
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "Agent URL is not allowed by outbound egress policy.",
    }


def test_signals_agent_add_refusal_reason_reaches_the_logs(
    authenticated_admin_client, seeded_tenant, monkeypatch, caplog
):
    """The reason withheld from the operator's screen is present in the operator's logs.

    Behaviour change (a): the flash no longer interpolates the reason, so the
    logs are now the only place it exists. Two records are required together —
    ``outbound_http`` knows why the address was refused but not which field it
    came from, and ``url_policy`` knows the field and the URL but not the
    reason. Either alone leaves an operator unable to act.
    """
    set_flags(monkeypatch)
    caplog.set_level(logging.WARNING)

    post_signals_agent(authenticated_admin_client, METADATA_URL)

    seam_records = [r for r in caplog.records if r.name == "src.core.security.outbound_http"]
    assert [r.getMessage() for r in seam_records if "169.254.169.254" in r.getMessage()], (
        f"the seam did not log the real refusal reason; got {[r.getMessage() for r in caplog.records]}"
    )
    admin_records = [r.getMessage() for r in caplog.records if r.name == "src.admin.utils.url_policy"]
    assert admin_records == [f"[SECURITY] Rejected Agent URL at ingest: {METADATA_URL!r}"]


# ---------------------------------------------------------------------------
# The JSON API shape: 400 with the generic error, and no reason in the body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, label",
    [
        ("slack_webhook_url", "Slack webhook URL"),
        ("slack_audit_webhook_url", "Slack audit webhook URL"),
        ("hitl_webhook_url", "HITL webhook URL"),
    ],
)
def test_create_tenant_refuses_blocked_webhook_url(field, label, management_api_client, monkeypatch, caplog):
    """Every webhook field on tenant creation is graded, and none is created.

    All three fields are parametrised because they are graded from one table:
    a field dropped from that table is a silently ungraded ingest point.
    """
    set_flags(monkeypatch)
    caplog.set_level(logging.WARNING)

    response = management_api_client.post(
        "/api/v1/tenant-management/tenants",
        headers={"X-Tenant-Management-API-Key": API_KEY},
        json={
            "name": "Refused Tenant",
            "subdomain": "refusedtenant",
            "ad_server": "mock",
            field: METADATA_URL,
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": f"{label} is not allowed by outbound egress policy."}
    assert [r.getMessage() for r in caplog.records if r.name == "src.admin.utils.url_policy"] == [
        f"[SECURITY] Rejected {label} at ingest: {METADATA_URL!r}"
    ]


def test_create_tenant_refusal_does_not_echo_the_reason(management_api_client, monkeypatch):
    """The 400 body carries nothing an attacker could read the network from.

    Point 6 is the obligation: the resolved IP and the resolve/reserved
    distinction together are an internal host and port scanner for whoever
    supplied the URL.
    """
    set_flags(monkeypatch)

    response = management_api_client.post(
        "/api/v1/tenant-management/tenants",
        headers={"X-Tenant-Management-API-Key": API_KEY},
        json={
            "name": "Refused Tenant",
            "subdomain": "refusedtenant",
            "ad_server": "mock",
            "slack_webhook_url": METADATA_URL,
        },
    )

    # The status is asserted here too, so a handler that stopped refusing
    # cannot pass this case by returning some other body with nothing to leak.
    assert response.status_code == 400
    body = response.get_data(as_text=True).lower()
    leaked = [fragment for fragment in LEAKED_FRAGMENTS if fragment in body]
    assert leaked == [], f"the 400 body leaked the refusal reason: {leaked}"


def test_update_tenant_refuses_blocked_webhook_url_and_stores_nothing(
    management_api_client, seeded_tenant, monkeypatch
):
    """Updating an existing tenant is graded too, and the column is left alone.

    Create and update are separate handlers; grading only one is how a
    write path ends up with no policy at all.
    """
    set_flags(monkeypatch)

    response = management_api_client.put(
        f"/api/v1/tenant-management/tenants/{TENANT_ID}",
        headers={"X-Tenant-Management-API-Key": API_KEY},
        json={"slack_webhook_url": METADATA_URL},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Slack webhook URL is not allowed by outbound egress policy."}

    session = seeded_tenant.get_session()
    session.rollback()
    tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
    assert tenant.slack_webhook_url is None


def test_update_tenant_accepts_a_url_egress_policy_admits(management_api_client, seeded_tenant, monkeypatch):
    """A URL the policy admits is written through — the JSON path's positive control."""
    set_flags(monkeypatch, private=True)

    response = management_api_client.put(
        f"/api/v1/tenant-management/tenants/{TENANT_ID}",
        headers={"X-Tenant-Management-API-Key": API_KEY},
        json={"slack_webhook_url": ADMITTED_URL},
    )

    assert response.status_code == 200

    session = seeded_tenant.get_session()
    session.rollback()
    tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
    assert tenant.slack_webhook_url == ADMITTED_URL


# ---------------------------------------------------------------------------
# Three more form-shape ingest sites, previously ungraded: a refactor could
# silently drop the ``redirect_if_url_blocked`` call from any of these and
# every other test in this suite would stay green.
# ---------------------------------------------------------------------------


def post_register_webhook(client, url: str):
    """POST the principal-webhook registration form with *url* as the target."""
    return client.post(
        f"/tenant/{TENANT_ID}/principals/{PRINCIPAL_ID}/webhooks/register",
        data={"url": url, "auth_type": "none"},
        follow_redirects=False,
    )


def push_notification_configs_for(env) -> list[PushNotificationConfig]:
    """Every registered webhook for the test principal, read fresh."""
    session = env.get_session()
    session.rollback()
    return list(
        session.scalars(select(PushNotificationConfig).filter_by(tenant_id=TENANT_ID, principal_id=PRINCIPAL_ID)).all()
    )


@pytest.mark.parametrize("url", [METADATA_URL, INSECURE_PUBLIC_URL])
def test_register_webhook_refuses_and_stores_nothing(url, authenticated_admin_client, seeded_principal, monkeypatch):
    """principals.py:625 — a principal's push-notification webhook is stored now,
    posted to later, and is graded the same as every other ingest site.
    """
    set_flags(monkeypatch)

    response = post_register_webhook(authenticated_admin_client, url)

    assert response.status_code == 302
    assert flashes(authenticated_admin_client) == [("error", "Webhook URL is not allowed by outbound egress policy.")]
    assert push_notification_configs_for(seeded_principal) == []


# No "accepts an admitted URL" positive control for this site: the handler's
# PushNotificationConfig(...) call uses field names that do not exist on the
# model (config_id/auth_type/auth_config instead of id/authentication_type/
# webhook_secret), so it raises on every real insert regardless of the URL —
# an unrelated pre-existing bug (salesagent-e4rf), not an SSRF-policy gap.
# The refusal-path test above still catches a dropped url_policy call, which
# is the obligation this file grades.


def post_creative_agent_add(client, url: str):
    """POST the creative-agent add form with *url* as the agent URL."""
    return client.post(
        f"/tenant/{TENANT_ID}/creative-agents/add",
        data={"agent_url": url, "name": "Ingest Policy Creative Agent", "priority": "10", "enabled": "on"},
        follow_redirects=False,
    )


def creative_agents_for(env) -> list[CreativeAgent]:
    """Every creative agent row for the test tenant, read fresh."""
    session = env.get_session()
    session.rollback()
    return list(session.scalars(select(CreativeAgent).filter_by(tenant_id=TENANT_ID)).all())


def create_creative_agent_through_the_add_form(client, env, monkeypatch) -> CreativeAgent:
    """Seed one creative agent by driving the real add endpoint.

    There is no ``CreativeAgentFactory``, and hand-writing the row would test a
    row this application never wrote — same rationale as the signals-agent seed
    helper above.
    """
    set_flags(monkeypatch, private=True)
    response = post_creative_agent_add(client, ADMITTED_URL)
    assert response.status_code == 302, "seeding the creative agent through the add form failed"
    agents = creative_agents_for(env)
    assert len(agents) == 1, f"expected exactly one seeded creative agent, got {agents}"
    return agents[0]


@pytest.mark.parametrize("url", [METADATA_URL, INSECURE_PUBLIC_URL])
def test_creative_agent_add_refuses_and_stores_nothing(url, authenticated_admin_client, seeded_tenant, monkeypatch):
    """creative_agents.py:105 — the add form."""
    set_flags(monkeypatch)

    response = post_creative_agent_add(authenticated_admin_client, url)

    assert response.status_code == 302
    assert "/creative-agents/add" in response.headers["Location"]
    assert flashes(authenticated_admin_client) == [("error", "Agent URL is not allowed by outbound egress policy.")]
    assert creative_agents_for(seeded_tenant) == []


def test_creative_agent_add_accepts_a_url_egress_policy_admits(authenticated_admin_client, seeded_tenant, monkeypatch):
    """A URL the policy admits is stored — the add form's positive control."""
    set_flags(monkeypatch, private=True)

    response = post_creative_agent_add(authenticated_admin_client, ADMITTED_URL)

    assert response.status_code == 302
    assert "/creative-agents/add" not in response.headers["Location"]
    stored = creative_agents_for(seeded_tenant)
    assert [agent.agent_url for agent in stored] == [ADMITTED_URL]


@pytest.mark.parametrize("url", [METADATA_URL, INSECURE_PUBLIC_URL])
def test_creative_agent_edit_refuses_and_leaves_the_stored_url_alone(
    url, authenticated_admin_client, seeded_tenant, monkeypatch
):
    """creative_agents.py:189 — the edit form.

    Unlike the signals-agent edit handler, this one checks before assigning
    ``agent.agent_url``, so the ORM object never holds the refused value — but
    that is exactly what could regress silently without a test reading the
    column back.
    """
    agent = create_creative_agent_through_the_add_form(authenticated_admin_client, seeded_tenant, monkeypatch)
    set_flags(monkeypatch)

    response = authenticated_admin_client.post(
        f"/tenant/{TENANT_ID}/creative-agents/{agent.id}/edit",
        data={"agent_url": url, "name": "Ingest Policy Creative Agent", "priority": "10", "enabled": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/edit" in response.headers["Location"]
    assert [stored.agent_url for stored in creative_agents_for(seeded_tenant)] == [ADMITTED_URL]


@pytest.mark.parametrize(
    "field, label",
    [
        ("slack_webhook_url", "Slack webhook URL"),
        ("slack_audit_webhook_url", "Slack audit webhook URL"),
    ],
)
def test_update_slack_refuses_blocked_webhook_url_and_stores_nothing(
    field, label, authenticated_admin_client, seeded_tenant, monkeypatch
):
    """settings.py:521,525 — the tenant-settings Slack integration form.

    Same fields as ``test_create_tenant_refuses_blocked_webhook_url`` above,
    but this is a second, independent handler (form POST, not the
    tenant-management JSON API) — grading only the JSON path would leave this
    one silently ungraded.
    """
    set_flags(monkeypatch)

    response = authenticated_admin_client.post(
        f"/tenant/{TENANT_ID}/settings/slack",
        data={field: METADATA_URL},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert flashes(authenticated_admin_client) == [("error", f"{label} is not allowed by outbound egress policy.")]

    session = seeded_tenant.get_session()
    session.rollback()
    tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
    assert tenant.slack_webhook_url is None
    assert tenant.slack_audit_webhook_url is None


def test_update_slack_accepts_a_url_egress_policy_admits(authenticated_admin_client, seeded_tenant, monkeypatch):
    """A URL the policy admits is stored — the Slack form's positive control."""
    set_flags(monkeypatch, private=True)

    response = authenticated_admin_client.post(
        f"/tenant/{TENANT_ID}/settings/slack",
        data={"slack_webhook_url": ADMITTED_URL},
        follow_redirects=False,
    )

    assert response.status_code == 302

    session = seeded_tenant.get_session()
    session.rollback()
    tenant = session.scalars(select(Tenant).filter_by(tenant_id=TENANT_ID)).one()
    assert tenant.slack_webhook_url == ADMITTED_URL
