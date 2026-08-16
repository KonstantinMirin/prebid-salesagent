"""Join BDD scenario liveness into the storyboard-checks pipeline (salesagent-vuz9t.12.2).

``storyboard_check_index`` derives ``covered_by`` from tag presence plus the
``@source`` footer alone — a ``@storyboard-v3.1``-tagged scenario with zero bound
step definitions has counted as "covered" forever, because nothing joined the
three liveness facts that already exist as data (salesagent-vuz9t.12's finding).
This module is that join:

* ``steps_bound`` — measured by a real ``pytest tests/bdd`` run, emitted by
  ``tests/bdd/scenario_liveness.py`` (salesagent-vuz9t.12.1) as
  ``test-results/bdd_scenario_liveness.json``.
* ``registry_wired`` — a DATA LOOKUP against the declarative
  ``tests.bdd.conftest.ENV_ROUTES`` registry (salesagent-vuz9t.11/.19), never
  reason-text matching. A scenario is registry-wired when its own ``T-*`` tag is a
  row (the SB-4a per-scenario demonstrator), or the ``UC-<n>`` bucket its
  ``T-UC-<n>...`` tag derives — the same derivation ``conftest._detect_uc`` uses
  for a tag matching that pattern — is a row, and that row isn't a placeholder
  (``EnvRoute.xfail_reason`` unset). The registry only covers a subset of UCs
  today (see ``ENV_ROUTES``'s own comment in conftest.py); a scenario whose UC
  isn't in the registry yet is ``registry_wired=False``, not "unknown" — this join
  is deliberately conservative, and will only grow more scenarios into
  ``graded_by_live_scenario`` as the registry widens. This is why the join
  replaces the artifact's own best-effort, reason-text-derived ``harness_wired``
  field rather than trusting it: that field is only as good as the auto-xfail
  reason text conftest happens to produce today, exactly what this task exists to
  stop relying on.
* ``ledgered`` — read straight from the artifact, itself already a join of the
  e2e_rest known-failures ledger and conftest's curated xfail-reason bucket
  (salesagent-vuz9t.12.1). Combined here with the conformance-ledger ``measured``
  column ``CheckRecord`` already carries (built from ``scripts/audit/ledger.py``'s
  ``load()`` against ``tests/storyboard/known_failures.txt`` — the third ledger)
  to flag a graduation candidate: a scenario we locally xfail as a known gap, for
  a check the real conformance run does not currently measure as failing.

A scenario absent from the artifact (no BDD run this session, or the run was
narrowed past it) is ``measured_this_run=False`` and reports
``steps_bound=False``/``ledgered=False`` — missing measurement renders as a gap,
never as a false "it's live" positive.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ARTIFACT_DEFAULT = Path("test-results") / "bdd_scenario_liveness.json"

# Mirrors tests/bdd/conftest.py's own _UC_TAG_RE exactly (the UC bucket a
# T-UC-<n>... tag derives). Kept as a literal so this module has no import-time
# dependency on conftest — only a deferred one, in load_env_routes(), for the
# ENV_ROUTES data itself.
_UC_TAG_RE = re.compile(r"^T-UC-(\d{3})(?:-|$)")


@dataclass(frozen=True)
class ScenarioLiveness:
    """One claiming scenario's joined liveness verdict."""

    scenario_id: str
    steps_bound: bool
    registry_wired: bool
    ledgered: bool
    measured_this_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_bound": self.steps_bound,
            "registry_wired": self.registry_wired,
            "ledgered": self.ledgered,
            "measured_this_run": self.measured_this_run,
        }

    @property
    def graded_by_live_scenario(self) -> bool:
        """The strict, join-backed liveness verdict.

        ``steps_bound`` alone (the parent finding's original "4-of-21" hand
        measurement) is not enough — a scenario whose harness routing isn't
        registry-verified stays ungraded, and a scenario the artifact never
        observed this run (``measured_this_run=False``) can never be graded by
        omission.
        """
        return self.measured_this_run and self.steps_bound and self.registry_wired


def load_env_routes() -> dict[str, Any]:
    """The declarative env-routing registry — pure data.

    Deferred import: this module has no import-time coupling to the pytest-bdd
    conftest it reads ``ENV_ROUTES`` from, and importing that module standalone
    (outside a pytest session) needs no database or fixture context — every
    heavier import in conftest.py lives inside a function body, not at module
    scope.
    """
    from tests.bdd.conftest import ENV_ROUTES

    return ENV_ROUTES


def registry_wired(scenario_id: str, env_routes: dict[str, Any]) -> bool:
    """Data lookup against ``ENV_ROUTES`` — no prose/reason-text parsing.

    Checks the scenario's own tag first (the SB-4a per-scenario demonstrator
    row), then the ``UC-<n>`` bucket a ``T-UC-<n>...`` tag derives. A row with
    ``xfail_reason`` set is a registered placeholder, not a real wire.
    """
    route = env_routes.get(scenario_id)
    if route is None:
        match = _UC_TAG_RE.match(scenario_id)
        if match:
            route = env_routes.get(f"UC-{match.group(1)}")
    return route is not None and route.xfail_reason is None


def default_artifact_path() -> Path:
    """Mirrors ``tests/bdd/scenario_liveness.py``'s own default/override contract."""
    override = os.environ.get("BDD_LIVENESS_ARTIFACT")
    return Path(override) if override else _ARTIFACT_DEFAULT


def load_artifact(path: Path) -> dict[str, dict[str, Any]]:
    """``scenario_id -> raw liveness record`` from a real ``pytest tests/bdd`` run.

    ``{}`` when the artifact is absent — every scenario then reports
    ``measured_this_run=False``, never silently assumed live.
    """
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s["scenario_id"]: s for s in data.get("scenarios", [])}


def build_index(
    scenario_ids: set[str],
    *,
    artifact_path: Path | None = None,
    env_routes: dict[str, Any] | None = None,
) -> dict[str, ScenarioLiveness]:
    """One :class:`ScenarioLiveness` per claiming scenario id."""
    artifact = load_artifact(artifact_path if artifact_path is not None else default_artifact_path())
    routes = env_routes if env_routes is not None else load_env_routes()
    index: dict[str, ScenarioLiveness] = {}
    for scenario_id in scenario_ids:
        record = artifact.get(scenario_id)
        index[scenario_id] = ScenarioLiveness(
            scenario_id=scenario_id,
            steps_bound=bool(record["steps_bound"]) if record is not None else False,
            registry_wired=registry_wired(scenario_id, routes),
            ledgered=bool(record["ledgered"]) if record is not None else False,
            measured_this_run=record is not None,
        )
    return index
