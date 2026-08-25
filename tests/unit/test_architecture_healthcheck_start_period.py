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

Read by parsing the compose YAML, NOT by shelling out to
`docker compose config`. The subprocess form is what this guard originally
used, on the reasoning that Docker's own resolution (env interpolation,
YAML anchors, `extends`) is the thing that actually runs. That reasoning is
sound in general and wrong here, for two independent reasons:

1. It made a UNIT test depend on the Docker CLI. `tests/unit/` runs inside
   the `tests` container, which has no docker binary — measured on both CI
   boxes at once (runs ba428471/4ce20dcd, 2026-08-25): all four cases died
   with `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`
   while passing on the developer's machine. A guard that only grades where
   Docker happens to be installed is a guard that stops grading in CI.
2. Nothing it bought applies to this assertion. `start_period` is a literal
   scalar; `${VAR}` interpolation cannot produce or remove it, and YAML
   anchors are resolved by the parser itself. The one construct that WOULD
   move a healthcheck between files is `extends:` — so this module asserts
   no compose file has grown one, rather than assuming it forever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

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

_COMPOSE_FILES = tuple(dict.fromkeys(f for f, _ in _MUST_HAVE_START_PERIOD))


def _load_compose(compose_file: str) -> dict[str, Any]:
    path: Path = repo_root() / compose_file
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolved_healthcheck(compose_file: str, service: str) -> dict:
    services = _load_compose(compose_file).get("services") or {}
    assert service in services, f"{compose_file} has no service {service!r} (services: {sorted(services)})"
    return services[service].get("healthcheck") or {}


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


@pytest.mark.arch_guard
@pytest.mark.parametrize("compose_file", _COMPOSE_FILES)
def test_compose_healthchecks_are_readable_without_docker(compose_file: str) -> None:
    """No service uses ``extends:``, so a plain YAML load resolves the same
    healthcheck Docker would.

    This is the assumption the module docstring rests on. ``extends`` is the
    only compose construct that can move a healthcheck in from another file
    (anchors are resolved by the YAML parser; ``${VAR}`` interpolation cannot
    add or remove a ``start_period`` key). If someone introduces one, this
    fails and the guard above must go back to Docker's own resolution — run
    somewhere that HAS Docker, which is not the unit suite.
    """
    services = _load_compose(compose_file).get("services") or {}
    extending = sorted(name for name, spec in services.items() if isinstance(spec, dict) and "extends" in spec)
    assert not extending, (
        f"{compose_file} services {extending} use `extends:`, which a plain yaml.safe_load does not "
        f"resolve — this module's healthcheck reads are no longer equivalent to `docker compose config`"
    )
