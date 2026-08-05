"""Structural guard: the e2e compose stack's outbound-only origins stay https.

salesagent-40qh gave the creative-agent origin in ``docker-compose.e2e.yml``
a real TLS front specifically so ``ADCP_OUTBOUND_ALLOW_INSECURE`` could
eventually close for it (salesagent-e6h0). A future edit reverting
``CREATIVE_AGENT_URL`` to plain http would silently re-introduce the disease
this ticket fixed — this guard catches that at ``make quality`` time instead
of at the next full e2e run.

salesagent-amht.3 replaced the per-launcher, env-configurable webhook
callback host (``ADCP_WEBHOOK_HOST``, with a ``host.docker.internal``
fallback) with a fixed compose-network alias (``webhooks.adcp.test``) behind
the shared TLS front — the same primitive ``CREATIVE_AGENT_URL`` already
uses. The check below is deliberately NOT a repoint of the old "does the
value end in .adcp.test" check (that would pass vacuously forever once the
var no longer exists to check); it instead guards the deletion itself — the
var reappearing anywhere in ``docker-compose.e2e.yml`` is the regression,
regardless of what value it would carry. The FULL generalized invariant —
one TLS terminator, every dialed origin https, one set of TLS material — is
salesagent-amht.5's explicit scope, not repeated here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _REPO_ROOT / "docker-compose.e2e.yml"


def find_tls_origin_violations(compose: dict) -> list[str]:
    """Return one message per service whose CREATIVE_AGENT_URL regressed to plain http."""
    violations: list[str] = []
    for service_name, service in compose.get("services", {}).items():
        env = service.get("environment") or {}
        if not isinstance(env, dict):
            continue
        creative_url = env.get("CREATIVE_AGENT_URL")
        if creative_url is not None and not str(creative_url).startswith("https://"):
            violations.append(f"{service_name}.CREATIVE_AGENT_URL is not https: {creative_url!r}")
    return violations


def find_dead_webhook_env_var(compose: dict) -> list[str]:
    """Return one message per service that resurrects the deleted ``ADCP_WEBHOOK_HOST`` mechanism.

    salesagent-amht.3 deleted this var entirely — the webhook-capture service
    is reachable at the fixed ``webhooks.adcp.test`` alias, never an
    env-configurable hostname. Its reappearance means a future change
    resurrected the per-launcher host-configuration disease this ticket removed.
    """
    violations: list[str] = []
    for service_name, service in compose.get("services", {}).items():
        env = service.get("environment") or {}
        if not isinstance(env, dict):
            continue
        if "ADCP_WEBHOOK_HOST" in env:
            violations.append(f"{service_name}.ADCP_WEBHOOK_HOST resurrected: {env['ADCP_WEBHOOK_HOST']!r}")
    return violations


def test_e2e_compose_creative_agent_stays_https() -> None:
    """The real docker-compose.e2e.yml has no plain-http regression on the creative-agent origin."""
    compose = yaml.safe_load(_COMPOSE_FILE.read_text())
    assert find_tls_origin_violations(compose) == []


def test_e2e_compose_never_resurrects_adcp_webhook_host() -> None:
    """The real docker-compose.e2e.yml never re-adds ADCP_WEBHOOK_HOST to any service."""
    compose = yaml.safe_load(_COMPOSE_FILE.read_text())
    assert find_dead_webhook_env_var(compose) == []


def test_detector_catches_a_reverted_creative_agent_url() -> None:
    """The live detector reports a synthetic CREATIVE_AGENT_URL reverted to plain http."""
    synthetic = {
        "services": {
            "adcp-server": {"environment": {"CREATIVE_AGENT_URL": "http://creative-agent:8080/api/creative-agent"}},
        }
    }
    assert find_tls_origin_violations(synthetic) == [
        "adcp-server.CREATIVE_AGENT_URL is not https: 'http://creative-agent:8080/api/creative-agent'"
    ]


def test_detector_catches_a_resurrected_adcp_webhook_host() -> None:
    """The live detector reports a synthetic ADCP_WEBHOOK_HOST resurrection, regardless of its value."""
    synthetic = {
        "services": {
            "tests": {"environment": {"ADCP_WEBHOOK_HOST": "tests.adcp.test"}},
        }
    }
    assert find_dead_webhook_env_var(synthetic) == ["tests.ADCP_WEBHOOK_HOST resurrected: 'tests.adcp.test'"]


def test_detector_ignores_unrelated_env_vars() -> None:
    """Unrelated service env vars (e.g. a plain-http health-check literal) are not flagged."""
    synthetic = {
        "services": {
            "proxy": {"environment": {"SOME_OTHER_URL": "http://localhost:8080/health"}},
        }
    }
    assert find_tls_origin_violations(synthetic) == []
    assert find_dead_webhook_env_var(synthetic) == []
