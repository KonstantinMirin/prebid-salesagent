"""Guard: recovery classification has exactly ONE source of truth — the pinned enum.

Three sources classify buyer-facing retry semantics today, and they disagree:

1. ``WIRE_STANDARD_CODES`` (``src/core/exceptions.py``) — the table
   ``advisory_recovery_for`` is being rewritten to read as its ONLY authority.
2. Each ``AdCPError`` subclass's ``_default_recovery`` — what a RAISED error
   carries onto the wire.
3. The pinned AdCP ``error-code.json`` ``enumMetadata`` — normative
   ("SDKs MUST consume this block ... the recovery classification embedded in
   that prose is normative and MUST match the value here").

The same wire code must mean the same thing to a buyer whether it arrived as a
raised error or as an advisory entry in ``errors[]``. Today it can differ: 7 of
the table's entries disagree with the pin, and 6 of those disagree with the
subclass that owns the code. The fix is the table fold (fold the spec-recovery
overrides INTO ``WIRE_STANDARD_CODES``); this file is what proves the fold
actually converged all three, and keeps them converged.

TDD-red note: assertions (2) and (3) below FAIL on the pre-fold tree — 7 and 6
offenders respectively, both enumerated in the failure messages. That is the
intended red. They must be made green by moving the TABLE onto the pin, never by
relaxing an assertion or by editing the pin.

DECLARED UNIT-TEST EXCEPTION (this project grounds behavior in BDD; a unit test
is not the default). Ratified for this file specifically, on the measured ground
that BDD grades the advisory recovery VALUE of only 2 of ~40 wire codes: this is
a static data-table/pin-parity assertion with no request surface a scenario can
reach, so it displaces no scenario — it accompanies them.

The pin is read THROUGH the SDK's own schema tree
(``tests/helpers/pinned_schema`` via ``_pinned_error_metadata``), the same
loader ``assert_wire_error`` grades every BDD error assertion against. A
hand-copied expectation dict is forbidden here: it would grade nothing but
itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from src.core.exceptions import WIRE_STANDARD_CODES, AdCPError
from tests.harness.transport import _pinned_error_metadata


class _RecoveryClaimant(Protocol):
    """Anything that claims a wire code with a recovery — an ``AdCPError`` subclass."""

    __name__: str
    _default_error_code: str
    _default_recovery: str


def _recovery_claims(classes: Iterable[Any]) -> dict[str, list[tuple[str, str]]]:
    """``{wire code: [(class name, declared recovery), ...]}`` for table-carried codes.

    Codes outside ``WIRE_STANDARD_CODES`` are internal-only (they never reach a
    buyer, and the table has no entry to compare against), so they are not
    collected — ``test_internal_only_codes_are_documented`` in
    ``test_architecture_error_recovery_enum_conformance.py`` is what keeps that
    set from growing unnoticed.
    """
    claims: dict[str, list[tuple[str, str]]] = {}
    for cls in classes:
        code = getattr(cls, "_default_error_code", None)
        if code in WIRE_STANDARD_CODES:
            claims.setdefault(code, []).append((cls.__name__, cls._default_recovery))
    return claims


def _production_claims() -> dict[str, list[tuple[str, str]]]:
    """Recovery claims made by every concrete ``AdCPError`` subclass in production."""
    return _recovery_claims(AdCPError.iter_concrete_subclasses())


def test_every_emittable_code_is_gradeable_against_the_pin() -> None:
    """Meta-guard: every wire code the table carries resolves in the pinned enum.

    Without this, a code the pin does not define would be silently skipped by the
    parity assertions below instead of graded — the failure mode that lets a table
    entry drift with the test still green.
    """
    meta = _pinned_error_metadata()
    ungradeable = sorted(code for code in WIRE_STANDARD_CODES if code not in meta)
    assert not ungradeable, (
        f"WIRE_STANDARD_CODES carries {ungradeable} which the pinned error-code.json "
        "enumMetadata does not define, so their recovery cannot be graded against the "
        "spec. Map them to a canonical code or advance the pin."
    )
    assert len(WIRE_STANDARD_CODES) >= 40, (
        f"Expected the wire-code table to carry many codes, got {len(WIRE_STANDARD_CODES)} — "
        "the parity assertions below would be near-vacuous."
    )


def test_table_recovery_matches_the_pin() -> None:
    """(1) Every ``WIRE_STANDARD_CODES`` entry's recovery equals the pinned enum's.

    This is the assertion the table fold exists to satisfy: once
    ``advisory_recovery_for`` is a pure lookup into this table, the table IS what a
    buyer is told about retryability for an advisory, so any entry that disagrees
    with the normative enumMetadata is a spec-nonconformant emission.
    """
    meta = _pinned_error_metadata()
    offenders = {
        code: (entry.get("recovery"), meta[code]["recovery"])
        for code, entry in sorted(WIRE_STANDARD_CODES.items())
        if code in meta and entry.get("recovery") != meta[code]["recovery"]
    }
    assert not offenders, (
        "WIRE_STANDARD_CODES recovery disagrees with the pinned error-code.json "
        "enumMetadata (normative) for "
        + ", ".join(f"{code}: table={table!r} pin={pin!r}" for code, (table, pin) in offenders.items())
        + ". Fold the spec recovery INTO the table — the table must derive from the pin, "
        "not carry an independent classification."
    )


def test_subclass_recovery_matches_the_table() -> None:
    """(2) Each subclass's ``_default_recovery`` equals its code's table recovery.

    The closing edge of the triangle, and NOT implied by grading each source
    against the pin separately: it is the only assertion that reads the two
    PRODUCTION sources against each other. A raised ``AdCPError`` carries the
    class value; an advisory entry for the same code carries the table value. If
    they differ, one buyer is told "retry" and another "do not" about the same
    wire code — which is precisely what collapsing the classification onto one
    table is meant to make impossible.
    """
    offenders = {
        code: (WIRE_STANDARD_CODES[code].get("recovery"), claimants)
        for code, claimants in sorted(_production_claims().items())
        if any(recovery != WIRE_STANDARD_CODES[code].get("recovery") for _, recovery in claimants)
    }
    assert not offenders, (
        "AdCPError subclass recovery disagrees with WIRE_STANDARD_CODES for "
        + "; ".join(
            f"{code}: table={table!r} vs " + ", ".join(f"{name}={recovery!r}" for name, recovery in claimants)
            for code, (table, claimants) in offenders.items()
        )
        + ". A raised error and an advisory carrying the same wire code must declare the "
        "same recovery."
    )


def test_no_code_is_claimed_twice_with_different_recovery() -> None:
    """(3) No two subclasses claim one wire code with conflicting recovery.

    Forward guard, green today by measurement — stated because the walk it
    replaces (``_iter_adcp_error_subclasses``, a depth-first ``stack.pop()``
    traversal) silently let ITERATION ORDER decide which of two claimants won.
    Deleting that walk removes the arbitrary tiebreak; this assertion makes a
    future tie a test failure instead of an invisible coin flip.
    """
    conflicts = {
        code: claimants
        for code, claimants in sorted(_production_claims().items())
        if len({r for _, r in claimants}) > 1
    }
    assert not conflicts, (
        "Wire code claimed by multiple AdCPError subclasses with DIFFERENT recovery: "
        + "; ".join(
            f"{code}: " + ", ".join(f"{name}={recovery!r}" for name, recovery in claimants)
            for code, claimants in conflicts.items()
        )
        + ". Which one wins would depend on subclass iteration order. Reconcile them "
        "against the pinned enum."
    )


class TestCollectorModelsTheForm:
    """Self-tests: ``_recovery_claims`` groups claimants the way the oracles assume.

    Deliberately NOT ``AdCPError`` subclasses — defining one at import time would
    add a synthetic class to ``iter_concrete_subclasses()`` and pollute every other
    oracle that walks that tree in the same process.
    """

    def test_groups_multiple_claimants_under_one_code(self) -> None:
        class _First:
            _default_error_code = "CONFIGURATION_ERROR"
            _default_recovery = "terminal"

        class _Second:
            _default_error_code = "CONFIGURATION_ERROR"
            _default_recovery = "transient"

        assert _recovery_claims([_First, _Second]) == {
            "CONFIGURATION_ERROR": [("_First", "terminal"), ("_Second", "transient")]
        }

    def test_drops_codes_the_wire_table_does_not_carry(self) -> None:
        class _InternalOnly:
            _default_error_code = "WORKFLOW_CREATION_FAILED"
            _default_recovery = "transient"

        assert "WORKFLOW_CREATION_FAILED" not in WIRE_STANDARD_CODES
        assert _recovery_claims([_InternalOnly]) == {}

    def test_collects_the_real_production_classes(self) -> None:
        """The production walk finds real claimants — the oracles above cannot
        degrade to zero graded codes without this failing first."""
        claims = _production_claims()
        assert len(claims) >= 25, f"Expected many wire codes to be claimed by a subclass, got {len(claims)}"
        assert ("AdCPConfigurationError", "terminal") in claims["CONFIGURATION_ERROR"]
