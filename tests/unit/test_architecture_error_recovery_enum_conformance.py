"""Oracle: every ``AdCPError`` subclass's ``_default_recovery`` matches the pinned
``error-code.json`` ``enumMetadata`` recovery classification (#1417).

The ``enumMetadata`` block is normative — its ``$comment`` states: "SDKs MUST
consume this block ... the recovery classification embedded in that prose is
normative and MUST match the value here." This oracle locks in the auth-family
recovery fix (#1417: ``AUTH_REQUIRED`` is ``correctable``) and prevents
any exception class from drifting away from the spec's buyer-facing retry
semantics. Per-class tests that assert a hardcoded literal cannot catch a
divergence between the class and the spec — this parametrized oracle does.

Codes absent from the pinned enum (internal/adapter-only codes that have no AdCP
wire equivalent — e.g. ``WORKFLOW_CREATION_FAILED``, ``GAM_UPDATE_FAILED``) cannot
be graded against an enum that does not contain them; they are reported by
``test_internal_only_codes_are_documented`` rather than silently skipped.

Reads the ``recovery`` field through ``tests.helpers.pinned_schema`` (the
installed SDK's own error-code.json), NOT the vendored fixture the sibling
``suggestion``-conformance oracle still uses. Verified before this migration:
the SDK's 92-code enum is a strict superset of the fixture's 64 (fixture-only
set is empty), and the ``recovery`` classification is IDENTICAL across all 64
shared codes (0 divergences; 30 AdCPError subclasses graded, unchanged before
and after) — the ``suggestion`` field is NOT identical across those same
codes (4 textual divergences), which is why only this reader migrated.
Reproduce the fixture count: ``uv run python3 -c "import json;
print(len(json.load(open('tests/fixtures/adcp_schemas_pinned/enums/error-code.json'))['enum']))"``
-> 64 (see docs/adcp-spec-version.md "Pinned schema sources" for the full measurement).

The final section extends the same oracle to ``src/``'s own wire-code tables:
``src.core.exceptions`` must expose ``RECOVERY_BY_WIRE_CODE``, machine-read from
the same normative ``enumMetadata`` block, and no other table in that module may
answer a recovery question. This file keeps its OWN independent load of the pin
(``_pinned_recovery_by_code`` below) and grades src's table against it — never
the reverse — so the oracle also catches a bug in src's loader.
"""

from __future__ import annotations

import pytest
from adcp.server.helpers import STANDARD_ERROR_CODES

from src.core.exceptions import ERROR_CODE_MAPPING, WIRE_STANDARD_CODES, AdCPError, translate_error_code
from tests.helpers import pinned_schema


def _pinned_recovery_by_code() -> dict[str, str]:
    """Return ``{error_code: recovery}`` from the pinned enumMetadata block."""
    meta = pinned_schema.load("error-code.json")["enumMetadata"]
    return {code: entry["recovery"] for code, entry in meta.items() if isinstance(entry, dict) and "recovery" in entry}


_RECOVERY_BY_CODE = _pinned_recovery_by_code()


def _adcp_error_subclasses() -> list[type[AdCPError]]:
    # Walk the concrete-subclass tree (the production single source of truth used by
    # tool_error_logging._build_error_code_to_status), not just the exceptions module
    # namespace — future-proofs the oracle against a subclass defined outside
    # exceptions.py that inspect.getmembers would silently miss. (#1417)
    return list(AdCPError.iter_concrete_subclasses())


_GRADED_CLASSES = sorted(
    (c for c in _adcp_error_subclasses() if c._default_error_code in _RECOVERY_BY_CODE),
    key=lambda c: c.__name__,
)


def test_pinned_enum_metadata_loaded() -> None:
    """Meta-guard: the pinned enum loaded and graded a representative set, so the
    parametrized oracle below can never silently degrade to zero cases."""
    assert len(_RECOVERY_BY_CODE) >= 50, (
        f"Expected the pinned enumMetadata to define recovery for many codes, got {len(_RECOVERY_BY_CODE)}"
    )
    assert len(_GRADED_CLASSES) >= 25, f"Expected to grade many AdCPError subclasses, got {len(_GRADED_CLASSES)}"


@pytest.mark.parametrize("cls", _GRADED_CLASSES, ids=lambda c: c.__name__)
def test_default_recovery_matches_pinned_enum(cls: type[AdCPError]) -> None:
    """Each subclass's ``_default_recovery`` must equal the pinned enum's normative recovery."""
    code = cls._default_error_code
    expected = _RECOVERY_BY_CODE[code]
    assert cls._default_recovery == expected, (
        f"{cls.__name__} (code {code!r}) declares recovery={cls._default_recovery!r} "
        f"but the pinned error-code.json enumMetadata says {expected!r}. The enumMetadata "
        f"recovery is normative (xc2j): fix the class, or advance the pin if the spec changed."
    )


# Classes whose _default_error_code is rewritten by ERROR_CODE_MAPPING before it
# reaches the wire. Base AdCPError is included explicitly: iter_concrete_subclasses
# yields descendants only, yet the base class is live on the wire via the
# normalize_to_adcp_error crash-wrap path at every transport boundary.
_REMAPPED_CLASSES = sorted(
    (c for c in [AdCPError, *AdCPError.iter_concrete_subclasses()] if c._default_error_code in ERROR_CODE_MAPPING),
    key=lambda c: c.__name__,
)


def test_remapped_classes_enumerated() -> None:
    """Meta-guard: every ERROR_CODE_MAPPING target is present in the pinned
    enumMetadata, so fixture drift can never silently un-grade the wire-recovery
    oracle below (a target missing from _RECOVERY_BY_CODE would KeyError, but
    only for classes that carry it — this pins the full target set)."""
    missing = sorted(set(ERROR_CODE_MAPPING.values()) - set(_RECOVERY_BY_CODE))
    assert not missing, (
        f"ERROR_CODE_MAPPING target(s) {missing} are absent from the pinned "
        f"error-code.json enumMetadata, so the wire-recovery oracle cannot grade "
        f"them. Advance the pinned fixture (the enum defines these codes upstream) "
        f"or fix the mapping."
    )
    assert len(_REMAPPED_CLASSES) >= 10, f"Expected to grade many remapped classes, got {len(_REMAPPED_CLASSES)}"


@pytest.mark.parametrize("cls", _REMAPPED_CLASSES, ids=lambda c: c.__name__)
def test_wire_recovery_matches_pinned_enum(cls: type[AdCPError]) -> None:
    """For every class whose default code is remapped by ERROR_CODE_MAPPING, the
    class's ``_default_recovery`` must equal the pinned enum's normative recovery
    for the code actually emitted on the wire (post-translation). The envelope
    builder emits ``exc.wire_error_code`` alongside ``exc.recovery`` — recovery
    follows the wire code, never the internal class taxonomy."""
    wire_code = translate_error_code(cls._default_error_code)
    expected = _RECOVERY_BY_CODE[wire_code]
    assert cls._default_recovery == expected, (
        f"{cls.__name__} (code {cls._default_error_code!r} -> wire {wire_code!r}) "
        f"declares recovery={cls._default_recovery!r} but the pinned error-code.json "
        f"enumMetadata says the wire code {wire_code!r} is {expected!r}. The envelope "
        f"emits the wire code with the class recovery, so this pair is spec-nonconformant "
        f"(nr2q): fix the class recovery or the mapping, or advance the pin if the spec changed."
    )


def test_internal_only_codes_are_documented() -> None:
    """Codes carried by exception classes but absent from the pinned enum are
    internal/adapter-only (no AdCP wire equivalent). Pin the known set so a NEW
    exception class with a non-spec code is surfaced for review rather than
    silently escaping the recovery oracle."""
    internal_codes = {
        c._default_error_code for c in _adcp_error_subclasses() if c._default_error_code not in _RECOVERY_BY_CODE
    }
    known_internal = {
        "NOT_FOUND",
        "TASK_NOT_FOUND",
        "FORMAT_NOT_FOUND",
        "WORKFLOW_CREATION_FAILED",
        "LINE_ITEM_CREATION_FAILED",
        "PARTIAL_FAILURE",
        "ACTIVATION_WORKFLOW_FAILED",
        "GAM_UPDATE_FAILED",
        "MEDIA_BUY_REJECTED",
        "INVENTORY_UNAVAILABLE",
    }
    unexpected = internal_codes - known_internal
    assert not unexpected, (
        f"New non-spec error code(s) {sorted(unexpected)} are not in the pinned enum and so "
        f"escape the recovery oracle. Either add the code to the AdCP error-code enum (and the "
        f"pin) or, if it is genuinely internal-only, add it to known_internal here."
    )


# ---------------------------------------------------------------------------
# src-side mirror: the production recovery table IS the pin, machine-read
# ---------------------------------------------------------------------------
# The normative enumMetadata block is currently machine-read only by this test
# helper, so nothing in src/ can consult it and every production recovery value
# is hand-typed. These three tests grade the src-side table that fixes that:
# it must equal the pin exactly, it must classify every code src can put on the
# wire, and it must be the ONLY table in exceptions.py that answers a recovery
# question (WIRE_STANDARD_CODES answers membership only).

# The two spec codes the SDK helper table has not caught up to; the pinned enum
# defines both (CREATIVE_NOT_FOUND correctable, CONFIGURATION_ERROR terminal),
# so they are wire codes src can emit and must therefore be classified.
_SUPPLEMENT_WIRE_CODES = frozenset({"CREATIVE_NOT_FOUND", "CONFIGURATION_ERROR"})


def _src_recovery_by_wire_code() -> dict[str, str]:
    """The production recovery table, imported inside the test body.

    Deliberately NOT a module-level import. While ``RECOVERY_BY_WIRE_CODE`` does
    not exist in src/, a module-level import would make this whole file a
    collection ERROR and silently un-grade the four oracles above; function-local,
    its absence is a FAILED result on the three obligations below and nothing else.
    """
    from src.core.exceptions import RECOVERY_BY_WIRE_CODE

    return RECOVERY_BY_WIRE_CODE


def test_src_recovery_table_mirrors_pinned_enum() -> None:
    """``src.core.exceptions.RECOVERY_BY_WIRE_CODE`` equals the pinned enumMetadata
    recovery block, code for code.

    Exact dict equality, not a size check: a loader that reads the wrong spec
    directory, drops the codes whose metadata shape differs, or falls back to the
    SDK helper's ``STANDARD_ERROR_CODES`` (which contradicts the pin on 7 of its
    38 codes) all produce a table of plausible size. This test loads the pin
    independently via ``tests.helpers.pinned_schema`` and never reads src's table
    as its own expectation, so it grades src's loader rather than agreeing with it.
    """
    pinned = _pinned_recovery_by_code()
    src_table = _src_recovery_by_wire_code()

    divergent = {
        code: {"src": src_table.get(code), "pin": pinned.get(code)}
        for code in sorted(set(pinned) | set(src_table))
        if src_table.get(code) != pinned.get(code)
    }
    assert src_table == pinned, (
        f"src.core.exceptions.RECOVERY_BY_WIRE_CODE diverges from the pinned "
        f"error-code.json enumMetadata on {len(divergent)} code(s): {divergent}. "
        f"The enumMetadata block is normative ($comment: 'SDKs MUST consume this "
        f"block instead of parsing Recovery: X from enumDescriptions prose') — load "
        f"it at import time; do not hand-type values and do not source them from "
        f"the SDK helper's STANDARD_ERROR_CODES."
    )


def test_src_recovery_table_covers_every_code_that_reaches_the_wire() -> None:
    """Every wire code src can emit has a classification in the src-side table.

    The codes that reach a buyer are the ERROR_CODE_MAPPING translation targets
    plus the pinned-spec supplement. A table that omits one of them makes the
    recovery answer a KeyError at exactly the moment a caller needs it.
    """
    src_table = _src_recovery_by_wire_code()

    emittable = set(ERROR_CODE_MAPPING.values()) | set(_SUPPLEMENT_WIRE_CODES)
    unclassified = sorted(emittable - set(src_table))
    assert not unclassified, (
        f"Wire code(s) {unclassified} can reach a buyer (ERROR_CODE_MAPPING target "
        f"or pinned-spec supplement) but carry no recovery classification in "
        f"src.core.exceptions.RECOVERY_BY_WIRE_CODE."
    )


def test_wire_standard_codes_carry_no_classification() -> None:
    """``WIRE_STANDARD_CODES`` answers membership only — one provenance rule.

    Every entry's value must be empty. The table is built from the SDK helper's
    ``STANDARD_ERROR_CODES``, whose recovery values contradict the pin on 7 codes
    (UNSUPPORTED_FEATURE, AUTHORIZATION_REQUIRED, IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_EXPIRED, BUDGET_EXHAUSTED, CONFLICT, ACCOUNT_PAYMENT_REQUIRED);
    keeping those values live in the module makes a future value read silently
    pin-contradicting for 7 codes instead of a loud KeyError for all of them.
    RECOVERY_BY_WIRE_CODE is the only classification either TABLE in exceptions.py
    carries. Two hand-typed surfaces remain outside the tables: the per-class
    ``_default_recovery`` literals, which the oracles above DO grade against this
    pin, and the ``recovery=`` constructor kwarg, which nothing grades — a call site
    can still pair a code with a recovery the pin contradicts.
    """
    classified = {code: entry for code, entry in WIRE_STANDARD_CODES.items() if entry != {}}
    assert not classified, (
        f"{len(classified)} WIRE_STANDARD_CODES entries still carry values "
        f"(e.g. {dict(sorted(classified.items())[:3])}). The table answers membership "
        f"only; recovery comes from RECOVERY_BY_WIRE_CODE, machine-read from the pin."
    )

    assert set(WIRE_STANDARD_CODES) == set(STANDARD_ERROR_CODES) | set(_SUPPLEMENT_WIRE_CODES), (
        "WIRE_STANDARD_CODES must stay the SDK helper's code-NAME baseline plus the "
        "pinned-spec supplement names — emptying the values must not change which "
        "codes are members."
    )
    assert len(WIRE_STANDARD_CODES) == 40, (
        f"WIRE_STANDARD_CODES has {len(WIRE_STANDARD_CODES)} entries, not 40 (38 SDK "
        f"+ 2 supplement). src/core/security/webhook_strict_json.py:102 documents the "
        f"40-entry count; update it together with this assertion if the SDK pin moves."
    )
