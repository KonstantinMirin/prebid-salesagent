"""The production image runs what it ships: its nginx, healthcheck and cron jobs reach real targets.

The image runs nginx on :8000 (the one EXPOSEd port) in front of the app on :8080, and
supercronic on ``/app/crontab``. Every compose file runs the image with ``SKIP_NGINX`` and
``SKIP_CRON``, so neither path is exercised by the stack the suites use; these checks read
the files the image is built from.
"""

from __future__ import annotations

import importlib
import re

import pytest

from tests.unit._architecture_helpers import repo_root

_APP_DIR = "/app/"  # Dockerfile: WORKDIR /app + COPY . .


def _dockerfile_lines() -> list[str]:
    return (repo_root() / "Dockerfile").read_text(encoding="utf-8").splitlines()


def test_healthcheck_probes_the_exposed_port() -> None:
    """A healthcheck on an internal port reports healthy while the public port is dead."""
    lines = _dockerfile_lines()
    exposed = {port for line in lines if line.startswith("EXPOSE ") for port in line.split()[1:]}
    healthcheck = next(i for i, line in enumerate(lines) if line.startswith("HEALTHCHECK "))
    command = lines[healthcheck] + lines[healthcheck + 1]  # the CMD continues the HEALTHCHECK line
    probed = re.findall(r"localhost:(\d+)", command)
    assert probed, f"HEALTHCHECK probes no localhost port: {command!r}"
    assert set(probed) <= exposed, f"HEALTHCHECK probes {probed}, image EXPOSEs {sorted(exposed)}"


@pytest.mark.parametrize("config", ["nginx-single-tenant.conf", "nginx-multi-tenant.conf"])
def test_image_nginx_pid_file_is_writable_by_the_runtime_user(config: str) -> None:
    """The image's nginx runs as USER app, and /run (where /var/run points) stays root-owned."""
    text = (repo_root() / "config" / "nginx" / config).read_text(encoding="utf-8")
    pid = re.search(r"^pid\s+(\S+);", text, re.MULTILINE)
    assert pid, f"{config} declares no pid file; nginx falls back to its root-owned default"
    assert pid.group(1).startswith("/tmp/"), f"{config}: pid {pid.group(1)} is not writable by the runtime user"


def test_every_crontab_target_exists_in_the_image() -> None:
    jobs = [
        line
        for line in (repo_root() / "crontab").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert jobs, "crontab has no jobs"
    targets = [token for job in jobs for token in job.split() if token.startswith(_APP_DIR)]
    assert targets, f"no crontab job names a file under {_APP_DIR}: {jobs}"
    missing = [t for t in targets if not (repo_root() / t.removeprefix(_APP_DIR)).is_file()]
    assert not missing, f"crontab runs files the image does not contain: {missing}"


def test_sync_job_posts_to_the_registered_trigger_route() -> None:
    """The cron script imports and its trigger URL resolves to the sync API's trigger view."""
    from src.admin.app import create_app

    script = importlib.import_module("scripts.ops.sync_all_tenants")
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
    endpoint, args = app.url_map.bind("localhost").match(script.SYNC_TRIGGER_PATH.format(tenant_id="t1"), method="POST")
    assert (endpoint, args) == ("sync_api.trigger_sync", {"tenant_id": "t1"})
