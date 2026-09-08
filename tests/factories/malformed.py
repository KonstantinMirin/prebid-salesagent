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
  here"; it asks the PINNED MODEL "is this payload valid", and then compares that
  verdict against what the declaration CLAIMS the verdict is. So a malformation nobody
  declared cannot hide, a declaration nobody can justify cannot be added without naming
  its kind and its reason, and a declaration that has stopped being true fails instead
  of being skipped.

WHY ``kind`` IS AUTHOR-SUPPLIED AND NOT DERIVED. The pinned model reports
``"format_id": None`` and a MISSING ``format_id`` key identically — both
``[type=oneOf]``, byte-identical message — because ``CreativeAssetRequest`` deliberately
weakened ``format_id`` to optional and moved the constraint into
``_exactly_one_format_identifier``. Nothing derived from the value can tell those two
apart, so the author is the only source of the distinction.

WHY ``why`` IS REQUIRED. Same reasoning ``structural_guard_marker_re``
(``tests/unit/_architecture_helpers.py``) already encodes: a bare marker is an opt-out,
not a justification.

WHY ``pin_rejects`` IS A SECOND AXIS AND NOT A PARTITION OF ``kind``. ``kind`` is the
SHAPE of the wrongness; whether the pinned model CATCHES that shape is independent of
it, and measured to span both verdicts within a single kind:
``uc006_sync_creatives.py``'s ``given_creative_with_invalid_format_id`` is ``semantic``
and the pin REJECTS it (``format_id.id`` fails ``^[a-zA-Z0-9_-]+$``), while a different
semantic case — an unknown but well-formed format id — the pin ACCEPTS. Deriving
enforceability from the kind therefore leaves the next spanning kind silently ungraded
(``wrong_type`` is the obvious candidate: pydantic coerces some wrong types and rejects
others). The author states both axes, and the gate grades the second one against what
the pin actually does.

THE GATE IS DELIBERATELY ASYMMETRIC — for UNDECLARED items. Model-rejects means a
declaration is REQUIRED. Model-accepts means a declaration is PERMITTED and never
demanded: ``assets: {}`` and ``name: ""`` are conformant payloads whose wrongness is
downstream, and a gate that demanded markers on schema-valid payloads would fire on
every conformant creative in the tree. DECLARED items are graded in BOTH directions,
which does not disturb that asymmetry: it is the declaration, not the payload, that is
being checked against the pin.

Enforced by ``tests/unit/test_architecture_marked_malformation.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ValidationError

from src.core.schemas.creative import CreativeAssetRequest
from src.core.schemas.pricing import PricingOption

#: The closed vocabulary of SHAPES. Every member is expressible AND distinguishable at a
#: call site, and every member is purely syntactic: none of them says anything about
#: whether the pinned model rejects the bytes. That verdict is ``pin_rejects``, declared
#: per INSTANCE, because it is a property of the instance — measured, ``semantic`` spans
#: both verdicts, and reading enforceability off the kind is what left one declared site
#: ungraded (see the module docstring).
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

    __slots__ = ("kind", "pin_rejects", "why")

    def __init__(self, kind: str, why: str, payload: dict[str, Any], pin_rejects: bool) -> None:
        super().__init__(payload)
        self.kind = kind
        self.why = why
        self.pin_rejects = pin_rejects

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"malformed({self.kind!r}, {self.why!r}, {dict(self)!r}, pin_rejects={self.pin_rejects!r})"


def malformed(kind: str, why: str, payload: dict[str, Any], *, pin_rejects: bool) -> _Malformed:
    """Declare *payload* a deliberate malformation of *kind*, because *why*.

    Raises rather than returning a defaulted marker: a marker that silently accepted a
    typo'd kind or an empty reason would be an opt-out wearing a justification's name.

    ``pin_rejects`` says whether the PINNED MODEL is expected to reject these exact
    bytes, and :func:`malformation_problems` grades that claim against what the model
    actually does. It is REQUIRED and has no default for the same reason ``why`` has
    none: a defaulted axis degrades silently to the unchecked behaviour it replaced —
    ``pin_rejects=False`` by default would re-open the repair hole on every site that
    forgot it, and ``True`` by default would report every downstream-wrongness
    declaration (``assets: {}``, ``name: ""``) as repaired.

    Deliberately NOT audited by the static detector in
    ``tests/unit/test_architecture_marked_malformation.py``, which requires ``kind`` and
    ``why`` to be literals at the site. Those two have no runtime oracle, so a
    non-literal hides them from every check there is. ``pin_rejects`` has one: whatever
    expression produces it, the gate compares the resulting value against the pin's real
    verdict, and a wrong value fails loudly at dispatch.
    """
    if kind not in MALFORMATION_KINDS:
        raise ValueError(f"unknown malformation kind {kind!r}; pick one of {sorted(MALFORMATION_KINDS)}")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("malformed() requires a non-empty reason: a bare marker is an opt-out, not a justification")
    if not isinstance(payload, dict):
        raise TypeError(f"malformed() wraps a dict payload, got {type(payload).__name__}")
    if not isinstance(pin_rejects, bool):
        raise TypeError(
            f"malformed() requires pin_rejects=True/False, got {type(pin_rejects).__name__}. It states "
            "whether the pinned model rejects these bytes, and the gate grades that claim."
        )
    return _Malformed(kind, why, payload, pin_rejects)


# ---------------------------------------------------------------------------
# The runtime gate
# ---------------------------------------------------------------------------

#: Request fields whose ITEMS are graded, and the identifier each item carries.
#:
#: A FIELD NAME, matched WHEREVER IT SITS in the request bag — not a top-level key.
#: ``creatives`` appears at the top level of ``sync_creatives`` and nested under
#: ``packages[].creatives`` on the media-buy verbs, and for a long time only the first
#: was graded. Measured on the baseline payload artifact
#: (``test-results/innet_080926_1859/``, 8182 collected / 8182 payload rows): 158 items
#: dispatched at the top level, 0 rejected by the pin; 6 dispatched under
#: ``packages[0].creatives``, 3 REJECTED. The position nobody watched carried 3 of the
#: 3 pin rejections in the entire corpus, and two of those were real ``asset_type``
#: defects that had to be found by validating the census instead (salesagent-b341x.15).
#:
#: The ITEM model is the same at every position, which is the point rather than a
#: simplification: the DTOs disagree about the nested slot —
#: ``AdCPPackageUpdate.creatives`` is ``list[adcp ... CreativeAsset]`` (strict) while
#: ``PackageRequest.creatives`` is ``list[src ... Creative]`` (permissive), so an item
#: the pinned request model rejects passes the CREATE-path DTO untouched and reaches
#: production as a raw dict. Grading the item against the pinned item model is the one
#: verdict that does not depend on which DTO happens to be holding it.
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


def _pin_rejection(model: type[BaseModel], item: dict[str, Any]) -> ValidationError | None:
    """The pinned model's verdict on *item*: the error it raised, or ``None`` if accepted."""
    try:
        model.model_validate(item)
    except ValidationError as exc:
        return exc
    return None


def _gated_items(node: Any, path: str = "") -> Iterator[tuple[str, type[BaseModel], dict[str, Any]]]:
    """Every gated item in *node*, as ``(site, model, item)``, at whatever depth it sits.

    DICTS AND LISTS ONLY. A ``dispatch_request`` bag routinely carries ``req=<a typed
    request model>``; that object came from a builder the pin has already run, and the
    gate's subject is the hand-built inline LITERAL, so reaching through attributes
    would grade the builder on every dispatch. Items inside a gated list are yielded,
    never descended into, so one item cannot be reported twice.

    *path* accumulates the position so the report can name it: ``creatives[0]`` at the
    top level, ``packages[0].creatives[0]`` nested — the same rendering a reader would
    use to subscript their way back to the payload.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            entry = GATED_ITEMS.get(key)
            if entry is not None and isinstance(value, list):
                model, id_key = entry
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        yield f"{child}[{index}] ({id_key}={item.get(id_key)!r})", model, item
            else:
                yield from _gated_items(value, child)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _gated_items(item, f"{path}[{index}]")


def malformation_problems(kwargs: dict[str, Any]) -> list[str]:
    """One message per dispatched item whose real verdict and declaration disagree.

    Three ways they can disagree, and the third is why this function no longer skips a
    declared item:

    * NOT DECLARED, and the pin rejects it — an undeclared malformation.
    * DECLARED ``pin_rejects=True``, and the pin ACCEPTS it — the malformation was
      REPAIRED. This is what a factory default does to a site whose migration dropped
      the override carrying the wrongness, and skipping declared items is what made it
      invisible.
    * DECLARED ``pin_rejects=False``, and the pin REJECTS it — MIS-DECLARED. The site
      claims the pin tolerates these bytes and it does not.

    Only ``dict`` items are graded. The subject is the hand-built inline LITERAL; a
    typed model instance in the same slot came from a builder that already validated it,
    and feeding one here would grade the builder rather than the literal.
    """
    problems: list[str] = []
    for site, model, item in _gated_items(kwargs):
        rejection = _pin_rejection(model, item)
        if not isinstance(item, _Malformed):
            if rejection is not None:
                problems.append(f"{site} is rejected by {model.__name__} but is not declared malformed:\n{rejection}")
        elif item.pin_rejects and rejection is None:
            problems.append(
                f"{site} is declared malformed({item.kind!r}, pin_rejects=True) but {model.__name__} "
                "ACCEPTS it — the malformation was REPAIRED and the scenario now grades a conformant "
                "payload. Something supplied what the declaration says is wrong: a factory default is "
                "the usual culprit, so express the malformation as a payload() OVERRIDE (assets=OMIT, "
                "format_id=None, ...) rather than relying on the baseline to leave it out.\n"
                f"declared because: {item.why}"
            )
        elif not item.pin_rejects and rejection is not None:
            problems.append(
                f"{site} is declared malformed({item.kind!r}, pin_rejects=False) but {model.__name__} "
                "REJECTS it — the declaration is MIS-DECLARED. Either the bytes changed, or "
                "pin_rejects was guessed rather than measured; the pin's own reason follows.\n"
                f"{rejection}"
            )
    return problems


def assert_declared_malformations(kwargs: dict[str, Any]) -> None:
    """Fail the scenario if a dispatched item and its declaration disagree with the pin."""
    problems = malformation_problems(kwargs)
    assert not problems, (
        f"{len(problems)} dispatched item(s) disagree with the pinned model about their own "
        "validity. Either the payload is a DEFECT — fix it — or the malformation is deliberate, "
        "in which case declare it at the step that builds it, with the verdict measured rather "
        "than guessed:\n\n"
        "    from tests.factories.malformed import malformed\n"
        "    creative_payload = malformed(\n"
        '        "wrong_type", "<why these exact bytes are the point>", {...}, pin_rejects=True\n'
        "    )\n\n" + "\n\n".join(problems)
    )
