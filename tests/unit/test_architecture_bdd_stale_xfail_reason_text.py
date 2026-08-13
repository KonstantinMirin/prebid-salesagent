"""Guard: UC-010 xfail reason TEXT must describe the actual measured failure, and the
mi0x v3.1.1 scenario cluster must not claim "graded" while dormant.

``tests/unit/test_architecture_bdd_no_stale_xfail_citations.py`` only checks TAG
MEMBERSHIP (is a scenario's tag still registered in one of the xfail structures) — it
does not validate that a *registered* tag's reason STRING actually names the failure
production currently produces, nor that a UC-010 tag claiming a graded "#1592
production gap" in its Gherkin comment has ever actually run against production
(``_uc010_wired_tags()``/``_UC010_WIRED_TAGS`` gate). This guard closes that gap:

    An xfail reason must describe the ACTUAL first failing assert measured on that
    transport, cite the specific GH issue that will make the scenario true (never a
    stale/umbrella one), and must be re-derived the moment the reason it was written
    stops being accurate. A scenario that never runs must not claim a graded result.

1. ``T-UC-010-main``'s ``_XFAIL_TAGS`` reason must not repeat the stale
   "supported_pricing_models, reporting_delivery_methods not emitted" claim: both
   derive correctly now, and the Then order in
   ``BR-UC-010-discover-seller-capabilities.feature`` fails on ``account.sandbox``
   before ever reaching those fields.

2. ``T-UC-010-targeting``'s reason must not claim "geo_postal_areas uses the deprecated
   boolean-alias shape" — ``_build_geo_postal_areas`` builds the native country-keyed
   map correctly.

3. The 4 mi0x-cluster v3.1.1 scenarios (``creative_multiplicity``,
   ``creative_agentic_flags``, ``governance_aware``, ``vendor_metric_optimization``) have
   no Given/When/Then step definitions yet, so they are correctly absent from
   ``_UC010_WIRED_TAGS`` and fast-xfail via the generic dormant fallback. Their Gherkin
   comments must say so honestly (DORMANT), not claim a graded "#1592 production gap"
   they never actually run against.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.test_architecture_bdd_no_stale_xfail_citations import _uc010_wired_tags

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFTEST_PATH = _REPO_ROOT / "tests" / "bdd" / "conftest.py"

_MI0X_TAGS: tuple[str, ...] = (
    "T-UC-010-v31-creative-multiplicity",
    "T-UC-010-v31-creative-agentic-flags",
    "T-UC-010-v31-governance-aware",
    "T-UC-010-v31-vendor-metric-optimization",
)


def _xfail_tags_reasons() -> dict[str, str]:
    """Every ``{tag: reason}`` pair in conftest.py's module-level ``_XFAIL_TAGS`` dict literal."""
    tree = ast.parse(_CONFTEST_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == "_XFAIL_TAGS":
                    assert node.value is not None, "_XFAIL_TAGS has no value"
                    assert isinstance(node.value, ast.Dict), "_XFAIL_TAGS is not a dict literal"
                    reasons: dict[str, str] = {}
                    for key, value in zip(node.value.keys, node.value.values, strict=True):
                        if (
                            isinstance(key, ast.Constant)
                            and isinstance(key.value, str)
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                        ):
                            reasons[key.value] = value.value
                    return reasons
    raise AssertionError(f"_XFAIL_TAGS not found at module level in {_CONFTEST_PATH}")


class TestUC010MainReasonAccuracy:
    """The reporting-delivery xfail reason must name the CURRENTLY measured failing assert.

    #1721: T-UC-010-main was SPLIT. Its one undeliverable assert moved to
    @T-UC-010-main-reporting-delivery, which is what carries the xfail now; the rest
    of T-UC-010-main executes un-xfailed. This class follows the assert to its new
    tag -- a reason-accuracy meta-test that kept grading the old tag would grade an
    entry that no longer exists, and would pass vacuously if the dict lookup were
    ever made forgiving.
    """

    def test_main_reason_names_the_measured_gap_not_the_split_out_one(self) -> None:
        """T-UC-010-main's own reason must name where it ACTUALLY stops.

        It stops at media_buy.portfolio.primary_channels (a harness write-through
        gap, #1871), not at reporting_delivery_methods -- which is the claim the
        pre-#1721 reason made, and which was never true: the scenario never
        reached that assert. A reason naming a later assert than the real one
        hides the real one.
        """
        reason = _xfail_tags_reasons()["T-UC-010-main"]
        assert "primary_channels" in reason, (
            f"T-UC-010-main's reason must name primary_channels as the measured gap. Got: {reason!r}"
        )
        assert "reporting_delivery_methods" not in reason, (
            "T-UC-010-main's reason still claims reporting_delivery_methods, which the scenario "
            f"never reaches -- that assert now lives in its own scenario. Got: {reason!r}"
        )

    def test_reason_names_reporting_delivery_methods_as_the_live_gap(self) -> None:
        reason = _xfail_tags_reasons()["T-UC-010-main-reporting-delivery"]
        assert "reporting_delivery_methods" in reason, (
            "The split scenario's reason must name media_buy.reporting_delivery_methods "
            f"as the live gap. Got: {reason!r}"
        )

    def test_reason_cites_the_signing_dependency_not_a_resolved_claim(self) -> None:
        """The gap is spec-gated on RFC 9421 webhook signing (#1291), and account.sandbox
        is long since resolved -- the reason must say the former and not the latter."""
        reason = _xfail_tags_reasons()["T-UC-010-main-reporting-delivery"]
        assert "#1291" in reason, f"The reason must cite the RFC 9421 signing dependency. Got: {reason!r}"
        assert "account.sandbox" not in reason, (
            f"The reason still claims the resolved account.sandbox gap. Got: {reason!r}"
        )


class TestUC010TargetingReasonAccuracy:
    """T-UC-010-targeting's reason must not repeat a falsified boolean-alias claim."""

    def test_reason_does_not_claim_boolean_alias_shape(self) -> None:
        reason = _xfail_tags_reasons()["T-UC-010-targeting"]
        assert "boolean-alias" not in reason, (
            "T-UC-010-targeting's reason still claims the deprecated boolean-alias "
            "shape; _build_geo_postal_areas builds the native country-keyed map. "
            f"Got: {reason!r}"
        )


_FEATURE_PATH = _REPO_ROOT / "tests" / "bdd" / "features" / "BR-UC-010-discover-seller-capabilities.feature"


class TestMi0xScenariosHonestlyDormant:
    """The 4 v3.1.1 mi0x-cluster scenarios (creative_multiplicity,
    creative_agentic_flags, governance_aware, vendor_metric_optimization) have no
    Given/When/Then step definitions yet. Wiring them into _UC010_WIRED_TAGS without
    those steps would make them fast-xfail with a FALSE reason (claiming a graded
    production gap on a scenario that never runs) -- the same defect class this guard
    exists to catch. Until the step definitions are written, the correct state is:
    absent from _UC010_WIRED_TAGS (so they run through the honest dormant-fallback
    reason), and their Gherkin comment must say DORMANT, not XFAIL-EXPECTED."""

    @pytest.mark.parametrize("tag", _MI0X_TAGS)
    def test_tag_is_not_wired_without_step_definitions(self, tag: str) -> None:
        wired = _uc010_wired_tags()
        assert tag not in wired, (
            f"{tag} is in _UC010_WIRED_TAGS but has no Given/When/Then step "
            "definitions -- wiring without steps produces a false xfail reason."
        )

    def test_feature_file_does_not_claim_a_graded_gap_for_the_mi0x_cluster(self) -> None:
        text = _FEATURE_PATH.read_text(encoding="utf-8")
        for tag in _MI0X_TAGS:
            tag_index = text.index(f"@{tag}")
            scenario_block = text[tag_index : tag_index + 2000]
            assert "XFAIL-EXPECTED" not in scenario_block, (
                f"{tag}'s scenario claims XFAIL-EXPECTED (graded) but has no step "
                "definitions and never runs -- comment must say DORMANT instead."
            )
