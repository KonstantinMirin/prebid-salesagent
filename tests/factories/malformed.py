"""The marked-malformation mechanism: a payload that IS the wrong bytes, and says so.

CORE INVARIANT
    A test payload that the pinned model REJECTS is either a declared malformation
    or a defect, and the difference is stated at the site where the payload is
    written.

Two halves live here, and neither works without the other:

* :func:`malformed` — the DECLARATION. A wrapper call rather than a comment or a
  sentinel value, for two measured reasons. A comment is invisible at runtime, and
  the check that finds unmarked malformations has to be a runtime check (source-level
  ``ast.literal_eval`` succeeds on 0 of the 40 creative literals in
  ``uc006_sync_creatives.py`` — every one holds a Name, Attribute, Call or f-string,
  so a static validation gate would pass vacuously green over 80% of the target). A
  sentinel VALUE would change what reaches the wire, and these scenarios exist to put
  the exact wrong bytes there — ``tests/harness/_base.py``'s ``json_safe`` states that
  contract: "a deliberately-malformed value still reaches the wire malformed, which is
  the entire point of dispatching raw." A dict SUBCLASS keeps the bytes identical while
  carrying an identity the dispatch seam can read. Naming precedent for expressing
  deliberate malformation as a call: ``sends_malformed_body()``
  (``tests/helpers/local_http_origin.py``).

* :func:`assert_declared_malformations` — the GATE. It never asks "is there a marker
  here"; it asks the PINNED MODEL "is this payload valid", and only consults the marker
  to decide whether an already-detected failure was intended. So a malformation nobody
  declared cannot hide, and a declaration nobody can justify cannot be added without
  naming its kind and its reason.

WHY ``kind`` IS AUTHOR-SUPPLIED AND NOT DERIVED. The pinned model reports
``"format_id": None`` and a MISSING ``format_id`` key identically — both
``[type=oneOf]``, byte-identical message — because ``CreativeAssetRequest`` deliberately
weakened ``format_id`` to optional and moved the constraint into
``_exactly_one_format_identifier``. Nothing derived from the value can tell those two
apart, so the author is the only source of the distinction.

WHY ``why`` IS REQUIRED. Same reasoning ``structural_guard_marker_re``
(``tests/unit/_architecture_helpers.py``) already encodes: a bare marker is an opt-out,
not a justification.

THE GATE IS DELIBERATELY ASYMMETRIC. Model-rejects means a marker is REQUIRED.
Model-accepts means a marker is PERMITTED and unenforced — ``assets: {}`` and
``name: ""`` are conformant payloads whose wrongness is downstream, and a gate that
demanded markers on schema-valid payloads would fire on every conformant creative in
the tree.

Enforced by ``tests/unit/test_architecture_marked_malformation.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from src.core.schemas.creative import CreativeAssetRequest
from src.core.schemas.pricing import PricingOption

#: The closed vocabulary. Every member is expressible AND distinguishable at a call
#: site; only the ones the pinned model rejects are ENFORCEABLE (see the asymmetry
#: note above): ``empty_dict`` and ``empty_string`` are accepted by the pin today.
MALFORMATION_KINDS: frozenset[str] = frozenset(
    {
        "wrong_type",  # right key, wrong Python type   ("assets": "a string")
        "explicit_none",  # key present, value None        ("format_id": None)
        "absent_key",  # key not present at all         (no "assets" key)
        "empty_dict",  # present but empty              ("assets": {})
        "empty_string",  # present but empty              ("name": "")
        "semantic",  # shaped right, means nothing    ("id": "invalid format!!!")
    }
)


class _Malformed(dict):
    """A dict that IS the wrong bytes, and says so.

    A ``dict`` subclass so every existing subscript, ``**``-splat, ``json.dumps`` and
    ``.setdefault`` at the wrapped call sites keeps working untouched and the payload
    reaches the wire byte-identical to the unwrapped literal.

    The marker is carried by IDENTITY, so it survives exactly as long as the object
    does: ``json_safe`` rebuilds dicts and drops the subclass, which is precisely why
    :func:`assert_declared_malformations` runs before it.
    """

    __slots__ = ("kind", "why")

    def __init__(self, kind: str, why: str, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.kind = kind
        self.why = why

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"malformed({self.kind!r}, {self.why!r}, {dict(self)!r})"


def malformed(kind: str, why: str, payload: dict[str, Any]) -> _Malformed:
    """Declare *payload* a deliberate malformation of *kind*, because *why*.

    Raises rather than returning a defaulted marker: a marker that silently accepted a
    typo'd kind or an empty reason would be an opt-out wearing a justification's name.
    """
    if kind not in MALFORMATION_KINDS:
        raise ValueError(f"unknown malformation kind {kind!r}; pick one of {sorted(MALFORMATION_KINDS)}")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("malformed() requires a non-empty reason: a bare marker is an opt-out, not a justification")
    if not isinstance(payload, dict):
        raise TypeError(f"malformed() wraps a dict payload, got {type(payload).__name__}")
    return _Malformed(kind, why, payload)


# ---------------------------------------------------------------------------
# The runtime gate
# ---------------------------------------------------------------------------

#: Request fields whose ITEMS are graded, and the identifier each item carries.
#:
#: ITEMS, never the whole DTO: a whole-DTO gate fires on every negative-path scenario
#: that deliberately omits ``idempotency_key`` or ``account`` — scenarios that are
#: correct as written and are not this gate's subject.
#:
#: The models are the pinned REQUEST models, reached by the paths verified in
#: salesagent-b341x.1's research: NOT ``adcp.types.Creative`` (that resolves to the
#: delivery-RESPONSE model, which is the original defect ``CreativeAssetRequest``'s
#: docstring records) and NOT ``adcp.types.PricingOption`` (a bare ``UnionType`` alias
#: with no ``model_validate``). ``test_gated_creative_model_is_the_pinned_request_item``
#: derives the creative entry from the registry DTO so a re-point fails loudly.
GATED_ITEMS: dict[str, tuple[type[BaseModel], str]] = {
    "creatives": (CreativeAssetRequest, "creative_id"),
    # No request DTO carries a top-level ``pricing_options`` today (it is a Product
    # RESPONSE field), so this entry grades nothing yet. It is declared anyway because
    # the gate's subject is "inline literals of a pinned item model" and pricing is the
    # second such literal the audit counts; the day a request grows the field, it is
    # graded rather than discovered.
    "pricing_options": (PricingOption, "pricing_option_id"),
}

#: THE GATE CARRIES NO TOLERANCE LIST, and that is a measured decision rather than an
#: omission. The five unmarked FIXABLE_NOW sites this mechanism was built for
#: (salesagent-hz7di.2's scan) all sit in scenarios that are xfail-DORMANT today
#: ("UC-006 harness not yet wired for non-account scenarios"), so with every tolerance
#: removed the gate fires ZERO times across every BDD module that dispatches a
#: top-level ``creatives`` bag — measured, 164 passed / 632 xfailed / 3 pre-existing
#: egress failures. A tolerance entry would therefore protect nothing today and would
#: MASK the malformation on the day its scenario is finally wired, which is precisely
#: when it starts to matter. The five sites are handed to salesagent-hz7di.4 through
#: ``KNOWN_VIOLATIONS`` in ``tests/unit/test_architecture_marked_malformation.py``,
#: where the staleness test grades the handoff without granting a runtime pass.


def undeclared_malformations(kwargs: dict[str, Any]) -> list[str]:
    """One message per dispatched item the pinned model rejects that nobody declared.

    Only ``dict`` items are graded. The subject is the hand-built inline LITERAL; a
    typed model instance in the same slot came from a builder that already validated it,
    and feeding one here would grade the builder rather than the literal.
    """
    problems: list[str] = []
    for field, (model, id_key) in GATED_ITEMS.items():
        items = kwargs.get(field)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if isinstance(item, _Malformed) or not isinstance(item, dict):
                continue
            try:
                model.model_validate(item)
            except ValidationError as exc:
                problems.append(
                    f"{field}[{index}] ({id_key}={item.get(id_key)!r}) is rejected by "
                    f"{model.__name__} but is not declared malformed:\n{exc}"
                )
    return problems


def assert_declared_malformations(kwargs: dict[str, Any]) -> None:
    """Fail the scenario if a dispatched item is malformed without saying so."""
    problems = undeclared_malformations(kwargs)
    assert not problems, (
        f"{len(problems)} dispatched item(s) the pinned model rejects carry no declaration.\n"
        "Either the payload is a DEFECT — fix it — or the malformation is deliberate, in "
        "which case wrap the literal at the step that builds it:\n\n"
        "    from tests.factories.malformed import malformed\n"
        "    creative_payload = malformed(\n"
        '        "wrong_type", "<why these exact bytes are the point>", {...}\n'
        "    )\n\n" + "\n\n".join(problems)
    )
