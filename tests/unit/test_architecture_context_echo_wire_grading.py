"""Guard: the context-echo obligation is graded against the CAPTURED WIRE.

Lane C item C5 (salesagent-qbac1.3): *context-echo tests assert against the
captured ``wire_response`` with an EXACT dict comparison — not
``response.context.model_dump(exclude_none=True)``, which is a re-serialization
that normalizes exactly what AdCP 3.1.1 echo rule 5 forbids.*

**Why a structural guard and not a behavioral test.** The obligation C5 states is
about the ASSERTION SOURCE, and a behavioral byte-for-byte echo test cannot
isolate it: measured on this tree, a caller-supplied
``context={"trace_id": "t1", "channel": None}`` comes back as
``{"trace_id": "t1"}`` on the MCP and A2A wire alike, so an exact-echo test
reddens on a PRODUCTION normalization defect that Lane C does not own and is not
authorized to fix. What Lane C owns is the test's own vacuity: an assertion
routed through ``model_dump(exclude_none=True)`` cannot see that difference at
all, because it applies the same normalization to the expectation. Grading the
source directly separates the two.

**Scope: the two sites C5 names, and no more.** Solution review pass 2, finding
(b), names ``tests/integration/test_context_echo_widened_fields.py``'s
``get_adcp_capabilities`` MCP and A2A echo tests specifically — both dispatch
through ``CapabilitiesEnv.call_mcp()`` / ``call_a2a()``, which return the typed
payload and carry NO WIRE AT ALL, so "compare the captured wire_response" is
impossible there without also moving the dispatch onto the wire-capturing seam
(``call_via`` / the post-Lane-B ``deliver_*`` primitives). That dispatch change is
part of C5. The sibling ``list_tasks`` tests already compare a plain dict and are
outside C5's stated scope; widening this guard to them would be scope the design
did not authorize.

The pinned site list can only SHRINK. A rename or deletion of either site fails
this guard loudly rather than silently reducing what is graded.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ECHO_TEST_FILE = _REPO_ROOT / "tests" / "integration" / "test_context_echo_widened_fields.py"

#: (class, method) of every context-echo assertion C5 places under this obligation.
#: Keyed by name, never line number — line anchors shift on unrelated edits.
_PINNED_ECHO_SITES: set[tuple[str, str]] = {
    ("TestGetAdcpCapabilitiesContextEcho", "test_context_echoed_through_mcp_wire"),
    ("TestGetAdcpCapabilitiesContextEcho", "test_context_echoed_through_a2a_wire"),
}

#: The guarded accessor / harness field that makes an echo assertion a real wire
#: read. ``TransportResult.wire_response`` is the success-path wire (tests/CLAUDE.md
#: "TransportResult.wire_response"); ``call_via`` is the dispatch that exposes it.
_WIRE_SOURCE_NAMES = ("wire_response", "wire_dict", "wire_field")


def _echo_sites() -> dict[tuple[str, str], ast.FunctionDef]:
    """Return every pinned echo test's AST node, keyed by (class, method)."""
    tree = ast.parse(_ECHO_TEST_FILE.read_text(encoding="utf-8"))
    found: dict[tuple[str, str], ast.FunctionDef] = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if isinstance(fn, ast.FunctionDef) and (cls.name, fn.name) in _PINNED_ECHO_SITES:
                found[(cls.name, fn.name)] = fn
    return found


@pytest.mark.arch_guard
def test_pinned_echo_sites_still_exist() -> None:
    """Guard the guard: a renamed or deleted site must fail, not silently un-grade itself."""
    missing = sorted(_PINNED_ECHO_SITES - set(_echo_sites()))
    assert missing == [], (
        f"Pinned context-echo site(s) no longer found in {_ECHO_TEST_FILE.relative_to(_REPO_ROOT)}: {missing}. "
        "If a site was renamed, move the pin with it; if it was deleted, the echo obligation it carried "
        "must be re-homed before the pin is dropped."
    )


@pytest.mark.arch_guard
def test_context_echo_is_asserted_against_the_captured_wire() -> None:
    """Each pinned echo assertion must read the captured wire, not re-serialize the payload."""
    violations: list[str] = []
    for (cls_name, fn_name), fn in sorted(_echo_sites().items()):
        names = {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)}
        names |= {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        if "model_dump" in names:
            violations.append(
                f"{cls_name}.{fn_name}: asserts through model_dump() — a re-serialization of the "
                "in-process object, which applies the same normalization to expectation and actual "
                "and so cannot grade AdCP 3.1.1's byte-for-byte echo rule"
            )
        if not names & set(_WIRE_SOURCE_NAMES):
            violations.append(
                f"{cls_name}.{fn_name}: never reads the captured wire "
                f"(expected one of {list(_WIRE_SOURCE_NAMES)}) — CapabilitiesEnv.call_mcp()/call_a2a() "
                "return the typed payload and carry no wire, so the dispatch must move onto the "
                "wire-capturing seam as part of this assertion change"
            )

    assert violations == [], "context-echo assertions must grade the wire:\n" + "\n".join(f"  {v}" for v in violations)
