"""Structural guard: the e2e compose stack's outbound-only origins stay https.

salesagent-40qh gave the creative-agent and webhook-capture origins in
``docker-compose.e2e.yml`` a real TLS front specifically so
``ADCP_OUTBOUND_ALLOW_INSECURE`` could eventually close for them
(salesagent-e6h0). A future edit reverting ``CREATIVE_AGENT_URL`` to plain
http, or ``ADCP_WEBHOOK_HOST`` to a bare (non-``.adcp.test``) alias, would
silently re-introduce the disease this ticket fixed — this guard catches that
at ``make quality`` time instead of at the next full e2e run.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _REPO_ROOT / "docker-compose.e2e.yml"


def find_tls_origin_violations(compose: dict) -> list[str]:
    """Return one message per service whose CREATIVE_AGENT_URL/ADCP_WEBHOOK_HOST regressed to plain http."""
    violations: list[str] = []
    for service_name, service in compose.get("services", {}).items():
        env = service.get("environment") or {}
        if not isinstance(env, dict):
            continue
        creative_url = env.get("CREATIVE_AGENT_URL")
        if creative_url is not None and not str(creative_url).startswith("https://"):
            violations.append(f"{service_name}.CREATIVE_AGENT_URL is not https: {creative_url!r}")
        webhook_host = env.get("ADCP_WEBHOOK_HOST")
        if webhook_host is not None and not str(webhook_host).endswith(".adcp.test"):
            violations.append(f"{service_name}.ADCP_WEBHOOK_HOST is not a .adcp.test alias: {webhook_host!r}")
    return violations


def test_e2e_compose_creative_agent_and_webhook_stay_https() -> None:
    """The real docker-compose.e2e.yml has no plain-http regression on either origin."""
    compose = yaml.safe_load(_COMPOSE_FILE.read_text())
    assert find_tls_origin_violations(compose) == []


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


def test_detector_catches_a_reverted_webhook_host_alias() -> None:
    """The live detector reports a synthetic ADCP_WEBHOOK_HOST reverted to the bare (non-TLS) alias."""
    synthetic = {
        "services": {
            "tests": {"environment": {"ADCP_WEBHOOK_HOST": "tests"}},
        }
    }
    assert find_tls_origin_violations(synthetic) == ["tests.ADCP_WEBHOOK_HOST is not a .adcp.test alias: 'tests'"]


def test_detector_ignores_unrelated_env_vars() -> None:
    """Unrelated service env vars (e.g. a plain-http health-check literal) are not flagged."""
    synthetic = {
        "services": {
            "proxy": {"environment": {"SOME_OTHER_URL": "http://localhost:8080/health"}},
        }
    }
    assert find_tls_origin_violations(synthetic) == []
