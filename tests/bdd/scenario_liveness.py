"""Emit the scenario-liveness artifact from a real BDD run (salesagent-vuz9t.12.1).

``storyboard_coverage_map.covered_storyboards`` (and the ``storyboard-checks.jsonl``
built on top of it) derives "covered" from tag presence plus the ``@source``
footer alone. Nothing in that path asks whether the scenario actually RUNS —
and ``tests/bdd/conftest.py``'s own auto-xfail hook converts
``StepDefinitionNotFoundError`` into ``xfail``, so a ``@storyboard-v3.1``-tagged
scenario with zero bound step definitions counts as coverage forever. This
module is the fix for the measurement, not the report: it emits, from a real
``pytest tests/bdd`` invocation, one liveness record per tagged scenario, and
each record carries the three facts the parent finding names:

* ``steps_bound`` — measured, not inferred. Computed by walking every step of
  the scenario through pytest-bdd's own ``get_step_function`` (the exact
  function ``_execute_scenario`` uses to decide whether to raise
  ``StepDefinitionNotFoundError``) *before* any step body runs, via the
  ``pytest_bdd_before_scenario`` hook. This checks every step, not just the
  first one pytest-bdd would fail on — a scenario whose first three steps are
  bound and fourth is not still reports ``steps_bound=False`` with the
  unbound step named, instead of silently stopping at the first failure the
  way a live run's exception would.
* ``harness_wired`` — a best-effort signal for this task, derived from the
  same auto-xfail reason text conftest.py already produces verbatim (e.g.
  ``"No harness wired for {uc}"``, ``"UC-004 harness not yet wired for type:
  ..."``). ``None`` when the scenario's steps aren't bound at all (the
  question is unreached: a step that doesn't even parse never gets to the
  harness-selection branch). Promoting this into a proper data lookup against
  the declarative ``ENV_ROUTES`` registry (no reason-text matching) is
  salesagent-vuz9t.12.2's job, once that registry covers more than its one
  demonstrator row.
* ``ledgered`` — True when the observation's reason falls into neither of the
  above two buckets (an explicit, curated ``xfail`` marker for a known
  production/spec gap), or the scenario's e2e_rest nodeid appears in
  ``tests/bdd/e2e_rest_known_failures.txt``. Joining this through the full
  three-ledger L0 loaders (``scripts/audit/ledger.py``) is also
  salesagent-vuz9t.12.2's job — this module only reads the one ledger BDD
  itself already loads.

Emits ``test-results/bdd_scenario_liveness.json`` (or
``$BDD_LIVENESS_ARTIFACT``) at session end — a per-run artifact, not a
checked-in one; test-results/ is gitignored. A run that never collects any
``@storyboard-v3.1``-tagged scenario (e.g. ``-k`` narrowed to something else)
writes an artifact with an empty ``scenarios`` list rather than skipping the
write — "the artifact didn't run this session" must be visible in the file
itself, not inferred from the file's absence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd.exceptions import StepDefinitionNotFoundError
from pytest_bdd.scenario import get_step_function

from tests.helpers.ledger import load_ledger_nodeids

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from pytest_bdd.parser import Feature, Scenario

# The same tag ``storyboard_spec.tagged_scenarios`` filters on — kept as a
# literal here (not imported from scripts/audit) so this pytest plugin has no
# import-time dependency on the audit CLI toolchain; both spellings are
# checked against ``docs/development/*`` by hand when either changes.
_TAG = "storyboard-v3.1"

_E2E_REST_LEDGER = Path(__file__).parent / "e2e_rest_known_failures.txt"
_LEDGERED_NODEIDS: frozenset[str] = load_ledger_nodeids(_E2E_REST_LEDGER)

_DEFAULT_ARTIFACT_PATH = Path("test-results") / "bdd_scenario_liveness.json"

_SCENARIO_ID_KEY = pytest.StashKey[str]()


@dataclass(frozen=True)
class Observation:
    """One (scenario, transport) run outcome."""

    transport: str
    nodeid: str
    outcome: str  # "passed" | "failed" | "xfailed"
    reason: str | None
    reason_category: str  # "live" | "no_steps_bound" | "harness_not_wired" | "ledgered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "nodeid": self.nodeid,
            "outcome": self.outcome,
            "reason": self.reason,
            "reason_category": self.reason_category,
        }


@dataclass
class ScenarioLiveness:
    """One ``@storyboard-v3.1``-tagged scenario's liveness, joined across transports."""

    scenario_id: str
    feature: str
    steps_bound: bool = True
    unbound_steps: list[str] = field(default_factory=list)
    harness_wired: bool | None = None
    ledgered: bool = False
    observations: list[Observation] = field(default_factory=list)

    def record_unbound(self, step_texts: list[str]) -> None:
        if not step_texts:
            return
        self.steps_bound = False
        for text in step_texts:
            if text not in self.unbound_steps:
                self.unbound_steps.append(text)

    def record_observation(self, obs: Observation) -> None:
        self.observations.append(obs)
        if obs.reason_category == "ledgered" or obs.nodeid in _LEDGERED_NODEIDS:
            self.ledgered = True
        if obs.reason_category == "harness_not_wired":
            self.harness_wired = False
        elif obs.reason_category in ("live", "ledgered") and self.harness_wired is not False:
            self.harness_wired = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "feature": self.feature,
            "steps_bound": self.steps_bound,
            "unbound_steps": self.unbound_steps,
            "harness_wired": self.harness_wired,
            "ledgered": self.ledgered,
            "observations": [o.to_dict() for o in self.observations],
        }


_RECORDS: dict[str, ScenarioLiveness] = {}


def _scenario_identifier(scenario: Scenario, feature: Feature) -> str | None:
    """The scenario's ``T-*`` identity tag, matching ``storyboard_spec``'s ``_IDENT_TAG_RE``."""
    for tag in scenario.tags | feature.tags:
        if tag.startswith("T-"):
            return tag
    return None


def _classify_reason(reason: str | None) -> str:
    """Bucket a captured xfail reason into the three categories the parent finding names.

    Grounded in conftest.py's actual, distinct code paths — not free-text
    guessing: ``StepDefinitionNotFoundError``/``NotImplementedError`` always
    produce the two literal prefixes matched below (the auto-xfail hookwrapper
    in ``tests/bdd/conftest.py`` builds them verbatim), and every
    harness-selection fallback raises ``pytest.xfail`` with a message
    containing both "harness" and "wired" (``_harness_env``'s catch-all and
    the UC-004 harness-type fallback). Anything else reaching xfail is an
    explicit, curated marker for a known gap — the residual "ledgered" bucket.
    """
    if reason is None:
        return "live"
    if reason.startswith("Step definition not found:") or reason.startswith("Not implemented:"):
        return "no_steps_bound"
    lowered = reason.lower()
    if "harness" in lowered and "wired" in lowered:
        return "harness_not_wired"
    return "ledgered"


def _transport_name(item: pytest.Item) -> str:
    """Best-effort transport label from the parametrized nodeid, e.g. ``mcp``."""
    nodeid = item.nodeid
    if "[" not in nodeid:
        return "default"
    param = nodeid.rsplit("[", 1)[-1].rstrip("]")
    return param.split("-", 1)[0] if param else "default"


def pytest_bdd_before_scenario(request: FixtureRequest, feature: Feature, scenario: Scenario) -> None:
    """Measure ``steps_bound`` for every step, before any step body executes.

    ``get_step_function`` is the exact lookup ``pytest_bdd._execute_scenario``
    uses to decide whether to raise ``StepDefinitionNotFoundError`` — calling
    it here only resolves the step-definition fixture (a ``StepFunctionContext``
    wrapper), it does not invoke the step's body, so this has no side effects
    on the scenario that is about to run.
    """
    tags = scenario.tags | feature.tags
    if _TAG not in tags:
        return
    scenario_id = _scenario_identifier(scenario, feature)
    if scenario_id is None:
        return

    record = _RECORDS.setdefault(scenario_id, ScenarioLiveness(scenario_id=scenario_id, feature=feature.rel_filename))
    unbound = [step.name for step in scenario.steps if get_step_function(request, step) is None]
    record.record_unbound(unbound)
    request.node.stash[_SCENARIO_ID_KEY] = scenario_id


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Any:
    """Record this item's outcome against the scenario ``pytest_bdd_before_scenario`` stashed.

    Reads ``report.wasxfail`` for marker-based/explicit ``pytest.xfail()``
    reasons (pytest's own regular hookimpls populate it during ``yield``,
    before any hookwrapper's post-yield code runs, so this is reliable
    regardless of registration order relative to conftest.py's own auto-xfail
    hookwrapper). For the two exception-based auto-xfail cases
    (``StepDefinitionNotFoundError``/``NotImplementedError``), ``wasxfail`` is
    only set by conftest.py's *own* hookwrapper post-yield — ordering between
    two hookwrappers is not guaranteed, so this derives the same signal
    independently from ``call.excinfo`` rather than depending on conftest.py
    having already run.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return

    scenario_id = item.stash.get(_SCENARIO_ID_KEY, None)
    if scenario_id is None:
        return
    record = _RECORDS.get(scenario_id)
    if record is None:
        return

    reason = getattr(report, "wasxfail", None)
    if reason is None and call.excinfo is not None:
        if call.excinfo.errisinstance(StepDefinitionNotFoundError):
            reason = f"Step definition not found: {call.excinfo.value}"
        elif call.excinfo.errisinstance(NotImplementedError):
            reason = f"Not implemented: {call.excinfo.value}"

    category = _classify_reason(reason)
    outcome_name = "passed" if report.passed else ("xfailed" if reason is not None else "failed")
    record.record_observation(
        Observation(
            transport=_transport_name(item),
            nodeid=item.nodeid,
            outcome=outcome_name,
            reason=reason,
            reason_category=category,
        )
    )


def artifact_path() -> Path:
    override = os.environ.get("BDD_LIVENESS_ARTIFACT")
    return Path(override) if override else _DEFAULT_ARTIFACT_PATH


def build_artifact() -> dict[str, Any]:
    return {"scenarios": [_RECORDS[k].to_dict() for k in sorted(_RECORDS)]}


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Write the per-run liveness artifact. Always writes, even if empty — see module docstring."""
    path = artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_artifact(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
