"""Every request factory's baseline payload is graded against the PINNED schema.

Why this suite exists rather than trusting the constructor
----------------------------------------------------------
A request factory's whole value is the promise "this payload is valid, so a test
that perturbs one field is grading that one field." Nothing enforced that promise
before, because the only available grade was "the Pydantic constructor accepted
it" — and our DTOs are the WEAKER of the two contracts in play. Measured against
the pin at the time of writing:

* ``media-buy/create-media-buy-request.json`` ``/required`` is
  ``[idempotency_key, account, brand, start_time, end_time]``;
  ``CreateMediaBuyRequest`` requires that set MINUS ``account``.
* ``account/sync-accounts-request.json`` ``/required`` is
  ``[idempotency_key, accounts]``; ``SyncAccountsRequest`` requires
  ``[accounts]`` alone.
* ``idempotency_key`` carries ``^[A-Za-z0-9_.:-]{16,255}$`` on the wire; the DTO
  types it as a bare ``str``, so a hand-written ``"test-key-1"`` constructs fine
  and is non-conformant.

So a baseline graded only by the constructor is graded against the contract that
asks for less. The factories supply the spec's fields regardless of what our DTOs
demand, and this suite is what keeps that true.

The allowlist
-------------
``_KNOWN_DIVERGENCES`` is the escape hatch for a baseline that departs from the
pin ON PURPOSE. It is a RATCHET, in the same shape as every other allowlist here:
rows carry a spec citation, rows are removed when the divergence is fixed, and
``test_every_allowlisted_divergence_is_still_live`` fails on a row that no longer
describes anything so a stale row cannot accumulate. The point of the mechanism
is not the rows it holds — it currently holds none — but that row two cannot be
added silently.

An empty allowlist is the GOOD state. Do not add a row to make a failure go away:
a divergence is allowlistable only if it is deliberate and documented somewhere
citable. An undocumented one is a bug in the factory or in the DTO.
"""

from __future__ import annotations

import pytest

from tests.factories.request import declared_request_factories, request_factories_by_tool
from tests.helpers.pinned_schema import validator_for
from tests.helpers.request_schemas import graded_request_schemas

#: ``(tool_name, json_path)`` -> the citation that makes the departure deliberate.
#:
#: ``json_path`` is the dotted ``absolute_path`` of the violation, ``"<root>"`` for
#: one reported at the top level (a missing required property reports there).
#: The citation must name the spec section or the source location that DECIDED
#: the divergence — e.g. "src/core/schemas/_base.py:2196 — identity resolves at
#: the transport layer (ResolvedIdentity), not from the payload".
#:
#: EMPTY ON PURPOSE. Every factory currently emits a fully conformant baseline.
_KNOWN_DIVERGENCES: dict[tuple[str, str], str] = {}


#: Tools that have BOTH a request factory and a pinned schema — the set this suite
#: grades. Both halves are derived (``request_factories_by_tool`` joins the MCP registry
#: to each factory's ``Meta.model``; ``graded_request_schemas`` derives the schema from
#: the DTO's SDK grounding), so a tool cannot be dropped from the grading by being left
#: out of a dict. A factory that lands in NEITHER is caught by
#: ``test_every_declared_factory_is_bound_to_a_registered_tool`` below.
def _graded_tools() -> list[str]:
    return sorted(set(request_factories_by_tool()) & set(graded_request_schemas()))


def _violations(tool_name: str) -> dict[str, str]:
    """``{json_path: message}`` for the tool's baseline payload against the pin."""
    payload = request_factories_by_tool()[tool_name].payload()
    validator = validator_for(graded_request_schemas()[tool_name][0])
    return {
        ".".join(str(part) for part in error.absolute_path) or "<root>": error.message
        for error in validator.iter_errors(payload)
    }


@pytest.mark.parametrize("tool_name", _graded_tools())
def test_the_baseline_payload_conforms_to_the_pinned_schema(tool_name: str) -> None:
    """The factory's unperturbed payload is one the spec would accept.

    This is the property every negative-path test leans on: perturb one field and
    the ONLY thing wrong with the request is that field.
    """
    schema_ref = graded_request_schemas()[tool_name][0]
    unexplained = {
        path: message for path, message in _violations(tool_name).items() if (tool_name, path) not in _KNOWN_DIVERGENCES
    }

    assert not unexplained, (
        f"{tool_name}'s baseline payload is not valid against {schema_ref}:\n"
        + "\n".join(f"  at {path}: {message}" for path, message in sorted(unexplained.items()))
        + "\n\nFix the factory. Add a row to _KNOWN_DIVERGENCES only if this departure is "
        "deliberate AND documented somewhere citable — the row must carry that citation."
    )


def test_every_declared_factory_is_bound_to_a_registered_tool_and_a_pinned_schema() -> None:
    """A factory cannot exist and go ungraded.

    The suite above parametrizes over the INTERSECTION of "has a factory" and "has a
    pinned schema", so a factory outside that intersection would simply not be
    collected — green, grading nothing. This is the half that notices. It replaces an
    assertion that a tool appeared in a hand-written schema table; the escape it closed
    was leaving a row out, and the escape it closes now is a factory whose model no
    registered tool builds, or one whose tool resolves no pinned schema.
    """
    graded = set(_graded_tools())
    bound = request_factories_by_tool()
    unbound = sorted(
        factory_class.__name__
        for model, factory_class in declared_request_factories().items()
        if factory_class not in {bound[tool] for tool in graded}
    )
    assert not unbound, (
        f"{unbound} declare a baseline payload that nothing grades against the pin. A "
        f"factory is graded when its Meta.model is the request DTO of a REGISTERED tool "
        f"AND that DTO resolves a pinned schema. Either the model is not built by any "
        f"tool, or its tool is ungraded — see "
        f"tests/unit/test_pydantic_schema_alignment.py::TestNoNonSpecFieldsAreAdvertised."
    )


def test_every_allowlisted_divergence_is_still_live() -> None:
    """The ratchet: a row that no longer describes a real violation must be deleted.

    Allowlists here only shrink. A row kept after its divergence is fixed
    re-permits the divergence silently the next time someone reintroduces it.
    """
    stale = [
        (tool_name, path)
        for (tool_name, path) in _KNOWN_DIVERGENCES
        if tool_name in _graded_tools() and path not in _violations(tool_name)
    ]
    assert not stale, (
        f"_KNOWN_DIVERGENCES rows no longer describe a violation: {stale}. The baseline now "
        f"conforms — delete the rows. Allowlists here only shrink."
    )


def test_every_allowlisted_divergence_carries_a_citation() -> None:
    """A row without a citation is an unexplained exemption wearing an allowlist's clothes."""
    uncited = sorted(key for key, citation in _KNOWN_DIVERGENCES.items() if not citation.strip())
    assert not uncited, (
        f"_KNOWN_DIVERGENCES rows with no citation: {uncited}. Name the spec section or the "
        f"source location that decided the departure."
    )
