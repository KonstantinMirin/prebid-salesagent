"""Guard: every curl-based healthcheck on a Python app server (adcp-server,
admin-ui) across every docker-compose*.yml declares a start_period.

Reported live: adcp-server showed as UNHEALTHY (surfaced loudly — it's a
REQUIRED service) during ordinary startup under heavy concurrent test load,
not because it was actually broken. Root cause: its healthcheck had no
start_period, so Docker starts counting failed checks from container start
with no grace window — a slow-to-warm-up container under load goes straight
to genuine `unhealthy` after `retries` failed checks, never through the
`starting` status a start_period would give it. cassini (the CI-offload
tool that surfaces this) already excludes `starting` from what it reports
as unhealthy; that only helps if the compose file actually gives Docker a
start_period to report `starting` during.

The bug wasn't confined to one file: the identical healthcheck shape
(curl .../health, interval 30s, timeout 10s, retries 3, no start_period)
was found in THREE compose files during this fix's own codebase-wide
disease scan — docker-compose.e2e.yml (the reported instance),
docker-compose.yml (local dev), and docker-compose.multi-tenant.yml
(adcp-server AND admin-ui). Parametrized across all four rather than
guarding only the one that was reported.

Read through `docker compose config` (Docker's own real resolution of
each file, including env-var interpolation and YAML anchors) rather than
a hand-parsed YAML load, so this checks what Docker will ACTUALLY run,
not what the source file happens to say before merging/interpolation.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.unit._architecture_helpers import repo_root

# (compose file, service) pairs found carrying this exact healthcheck shape.
# postgres/proxy/creative-pg are deliberately NOT here: pg_isready/curl
# against their OWN lightweight process is a different, faster-starting
# risk profile than a whole Python app server warming up under load.
# creative-agent already has start_period: 30s and is the existing correct
# pattern these instances are being brought in line with.
_MUST_HAVE_START_PERIOD = (
    ("docker-compose.e2e.yml", "adcp-server"),
    ("docker-compose.yml", "adcp-server"),
    ("docker-compose.multi-tenant.yml", "adcp-server"),
    ("docker-compose.multi-tenant.yml", "admin-ui"),
)


def _resolved_healthcheck(compose_file: str, service: str) -> dict:
    out = subprocess.run(
        ["docker", "compose", "-f", compose_file, "config", "--format", "json"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)["services"][service].get("healthcheck") or {}


@pytest.mark.arch_guard
@pytest.mark.parametrize(
    "compose_file,service", _MUST_HAVE_START_PERIOD, ids=[f"{f}:{s}" for f, s in _MUST_HAVE_START_PERIOD]
)
def test_app_server_healthcheck_has_a_start_period(compose_file: str, service: str) -> None:
    hc = _resolved_healthcheck(compose_file, service)
    assert hc.get("start_period"), (
        f"{compose_file}:{service}'s healthcheck has no start_period — Docker will mark "
        f"ordinary, slow startup under load as genuinely unhealthy rather than 'starting' "
        f"(resolved healthcheck: {hc!r})"
    )
