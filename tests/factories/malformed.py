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

WHY THE SECOND AXIS IS AN OBLIGATION AND NOT A BOOLEAN. ``kind`` is the SHAPE of the
wrongness; what the SELLER owes the buyer for those bytes is independent of it, and
measured to span both answers within a single kind: ``uc006_sync_creatives.py``'s
``given_creative_with_invalid_format_id`` is ``semantic`` and the pin REJECTS it
(``format_id.id`` fails ``^[a-zA-Z0-9_-]+$``), while a different semantic case — an
unknown but well-formed format id — the pin ACCEPTS and the seller's own rules refuse.
Deriving the obligation from the kind therefore leaves the next spanning kind silently
ungraded (``wrong_type`` is the obvious candidate: pydantic coerces some wrong types
and rejects others).

That axis used to be the boolean ``pin_rejects``, and the boolean was one answer over
two questions. MEASURED on ``CreativeAssetRequest``, where the extra mode comes from
``get_pydantic_extra_mode()`` (``src/core/config.py``):

    ENVIRONMENT=development   extra=forbid    extra key only -> REJECTED [extra_forbidden]
                                              missing assets -> REJECTED [missing]
    ENVIRONMENT=production    extra=ignore    extra key only -> ACCEPTED
                                              missing assets -> REJECTED [missing]

So ``pin_rejects=True`` meant two different things depending on WHY the pin refused,
and only one of them was a property of the bytes: a declaration on an undeclared-key
site was correct in development and made this gate announce the malformation REPAIRED
in production, from the same literal, with the failure text naming neither environment.

``obligation`` replaces it with the thing a scenario author actually needs — WHICH WIRE
CODE the buyer must receive, so a Then can be written:

    ErrorCode.INVALID_REQUEST    the pin refuses the bytes ON THEIR MERITS (a required
                                 field missing, a wrong type, a violated constraint).
    ErrorCode.VALIDATION_ERROR   the bytes are well-formed and the SELLER'S RULES refuse
                                 them (``assets: {}``, ``name: ""``).

Both are environment-independent, which is the property the boolean lacked. They are
``adcp.types.ErrorCode`` members rather than a private vocabulary, so the axis cannot
name a code the wire has never heard of.

AN UNDECLARED KEY IS NOT A MALFORMATION, and the gate REFUSES a declaration on one
rather than offering a third member. A malformation is bytes the model refuses on their
merits; an undeclared key is bytes the boundary STRIPS. Its obligation is neither of the
two surfaces above — not the development raise, not the production drop — but the
architectural guarantee at ``src/core/schemas/_base.py``'s
``_accept_only_declared_fields`` that the field NEVER REACHES THE IMPLEMENTATION, which
is environment- and transport-independent and is graded by
``tests/unit/test_deep_strip.py`` and ``tests/harness/test_forward_compat_acceptance.py``.
A tri-state would preserve the collapse in a longer spelling; a refusal points the
author at the surface that can actually grade the claim.

THE GATE IS DELIBERATELY ASYMMETRIC — for UNDECLARED items. Model-rejects-on-the-merits
means a declaration is REQUIRED. Model-accepts means a declaration is PERMITTED and
never demanded: ``assets: {}`` and ``name: ""`` are conformant payloads whose wrongness
is downstream, and a gate that demanded markers on schema-valid payloads would fire on
every conformant creative in the tree. An undeclared item refused ONLY for an undeclared
key demands nothing either, for the reason above and because demanding it would make
this gate's own verdict depend on ``ENVIRONMENT``. DECLARED items are graded in BOTH
directions, which does not disturb that asymmetry: it is the declaration, not the
payload, that is being checked against the pin.

Enforced by ``tests/unit/test_architecture_marked_malformation.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from adcp.types import ErrorCode
from pydantic import BaseModel, ValidationError

from src.core.schemas.creative import CreativeAssetRequest
from src.core.schemas.pricing import PricingOption

#: The two obligations a declared malformation can carry: which code the buyer must
#: receive for these bytes. ``adcp.types.ErrorCode`` members rather than local strings,
#: so the axis cannot name a code the wire has never heard of, and a Then step can
#: assert the same object the boundary emits.
#:
#: There is no third member for an undeclared key. See the module docstring: that is not
#: a malformation, and :func:`malformation_problems` refuses a declaration on one.
MALFORMATION_OBLIGATIONS: frozenset[ErrorCode] = frozenset({ErrorCode.INVALID_REQUEST, ErrorCode.VALIDATION_ERROR})

#: The pydantic error type that means "the pin refused this key, not these bytes". The
#: ONE place the discriminator is spelled; it is read from ``ValidationError.errors()``,
#: which has carried it all along — the previous gate computed it and threw it away into
#: a message string.
_UNDECLARED_KEY = "extra_forbidden"

#: The closed vocabulary of SHAPES. Every member is expressible AND distinguishable at a
#: call site, and every member is purely syntactic: none of them says anything about
#: what the seller owes the buyer for the bytes. That is ``obligation``, declared per
#: INSTANCE, because it is a property of the instance — measured, ``semantic`` spans
#: both obligations, and reading the obligation off the kind is what left one declared
#: site ungraded (see the module docstring).
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

    __slots__ = ("kind", "obligation", "why")

    def __init__(self, kind: str, why: str, payload: dict[str, Any], obligation: ErrorCode) -> None:
        super().__init__(payload)
        self.kind = kind
        self.why = why
        self.obligation = obligation

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"malformed({self.kind!r}, {self.why!r}, {dict(self)!r}, obligation={self.obligation!r})"


def malformed(kind: str, why: str, payload: dict[str, Any], *, obligation: ErrorCode) -> _Malformed:
    """Declare *payload* a deliberate malformation of *kind*, because *why*.

    Raises rather than returning a defaulted marker: a marker that silently accepted a
    typo'd kind or an empty reason would be an opt-out wearing a justification's name.

    ``obligation`` says WHICH CODE the buyer must receive for these exact bytes —
    ``INVALID_REQUEST`` when the pinned model refuses them on their merits,
    ``VALIDATION_ERROR`` when they are well-formed and the seller's rules refuse them —
    and :func:`malformation_problems` grades that claim against what the model actually
    does. It is REQUIRED and has no default for the same reason ``why`` has none: a
    defaulted axis degrades silently to the unchecked behaviour it replaced. It is also
    the only half of the declaration a scenario author can act on: a site that says
    nothing about the obligation tells the next Then nothing about which
    ``assert_envelope_shape`` to write, which is the whole point of declaring.

    Deliberately NOT audited by the static detector in
    ``tests/unit/test_architecture_marked_malformation.py``, which requires ``kind`` and
    ``why`` to be literals at the site. Those two have no runtime oracle, so a
    non-literal hides them from every check there is. ``obligation`` has one: whatever
    expression produces it, the gate compares the resulting value against the pin's real
    verdict, and a wrong value fails loudly at dispatch.
    """
    if kind not in MALFORMATION_KINDS:
        raise ValueError(f"unknown malformation kind {kind!r}; pick one of {sorted(MALFORMATION_KINDS)}")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("malformed() requires a non-empty reason: a bare marker is an opt-out, not a justification")
    if not isinstance(payload, dict):
        raise TypeError(f"malformed() wraps a dict payload, got {type(payload).__name__}")
    # isinstance FIRST, and it is not belt-and-braces. ``ErrorCode`` is a ``StrEnum``
    # whose value IS its name, so the bare string "INVALID_REQUEST" compares equal to
    # the member and would sail through the membership test below — while
    # :func:`malformation_problems` compares with ``is``, so the declaration would be
    # graded by neither branch and the site would go silently unchecked. That is the
    # exact silent degradation this axis exists to end.
    if not isinstance(obligation, ErrorCode) or obligation not in MALFORMATION_OBLIGATIONS:
        raise ValueError(
            f"malformed() requires obligation={' or '.join(sorted(o.name for o in MALFORMATION_OBLIGATIONS))}, "
            f"got {obligation!r}. It states WHICH CODE the buyer must receive for these bytes, and the gate "
            "grades that claim against the pinned model. An undeclared key is not a malformation and has no "
            "member here — see this module's docstring."
        )
    return _Malformed(kind, why, payload, obligation)


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


def _obligation_of(rejection: ValidationError | None) -> ErrorCode | None:
    """What the pin's verdict OBLIGES, or ``None`` when it obliges nothing here.

    * accepted — the bytes are well-formed, so whatever is wrong with them is the
      SELLER'S rules to refuse: ``VALIDATION_ERROR``.
    * refused, and at least one reason is something other than an undeclared key — the
      pin refuses the bytes ON THEIR MERITS: ``INVALID_REQUEST``.
    * refused ONLY because of undeclared keys — ``None``. Not a malformation, and not
      this gate's obligation to grade; see the module docstring.

    THE FULL ERROR SET, NEVER ``errors()[0]``. One payload raises both ``missing`` and
    ``extra_forbidden`` routinely, and reading the first error makes the classification
    depend on an emission order pydantic does not contract. MEASURED on
    ``CreativeAssetRequest`` today: ``extra_forbidden`` is emitted LAST in every mixed
    case constructible against it (``missing`` + extra, ``string_pattern_mismatch`` +
    extra), so ``errors()[0]`` happens to agree — which is the kind of accident that
    stops being true silently, and reading the first error is what produced two
    contradictory measurements of this model in a single day.

    THE ONE THING STILL ENVIRONMENT-SENSITIVE, stated rather than hidden: the third
    branch can only fire where extras are VISIBLE. Under ``ENVIRONMENT=production``
    (``extra='ignore'``) an extra key raises nothing, so a declaration on such a site
    reads as an accepted payload and is graded ``VALIDATION_ERROR`` instead of refused.
    That is silence, not a contradiction — the defect being fixed here was a boolean
    that called the SAME literal honest in development and REPAIRED in production. BDD
    runs with extras forbidden, which is where the refusal has to fire.
    """
    if rejection is None:
        return ErrorCode.VALIDATION_ERROR
    reasons = {error["type"] for error in rejection.errors()}
    if reasons <= {_UNDECLARED_KEY}:
        return None
    return ErrorCode.INVALID_REQUEST


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
    """One message per dispatched item whose real obligation and declaration disagree.

    Four ways they can disagree. The first is the original half; the next two are why
    this function does not skip a declared item; the fourth is the one an author cannot
    talk their way past:

    * NOT DECLARED, and the pin refuses the bytes ON THEIR MERITS — an undeclared
      malformation.
    * DECLARED ``INVALID_REQUEST``, and the pin ACCEPTS — the malformation was REPAIRED.
      This is what a factory default does to a site whose migration dropped the override
      carrying the wrongness, and skipping declared items is what made it invisible.
    * DECLARED ``VALIDATION_ERROR``, and the pin REFUSES on the merits — MIS-DECLARED.
      The site claims the pin tolerates these bytes and it does not.
    * DECLARED at all, when the pin's ONLY objection is an undeclared key — REFUSED. Not
      a malformation; the message names the guarantee that does grade it.

    An UNDECLARED item whose only problem is an undeclared key demands nothing, which is
    the same rule seen from the other side: grading it here would make this gate's
    verdict depend on ``ENVIRONMENT`` (forbid in development, ignore in production) on a
    payload whose real obligation is environment-independent.

    Only ``dict`` items are graded. The subject is the hand-built inline LITERAL; a
    typed model instance in the same slot came from a builder that already validated it,
    and feeding one here would grade the builder rather than the literal.
    """
    problems: list[str] = []
    for site, model, item in _gated_items(kwargs):
        rejection = _pin_rejection(model, item)
        obliged = _obligation_of(rejection)
        if not isinstance(item, _Malformed):
            if obliged is ErrorCode.INVALID_REQUEST:
                problems.append(f"{site} is rejected by {model.__name__} but is not declared malformed:\n{rejection}")
        elif obliged is None:
            problems.append(
                f"{site} is declared malformed({item.kind!r}, obligation={item.obligation.name}) but the only "
                f"thing {model.__name__} objects to is an UNDECLARED KEY, which is not a malformation. A "
                "malformation is bytes the model refuses on their merits; an undeclared key is bytes the "
                "boundary STRIPS. That surface is environment-SPECIFIC — ENVIRONMENT=production sets "
                "extra='ignore' (get_pydantic_extra_mode, src/core/config.py) and these same bytes are "
                "ACCEPTED there — so this declaration is correct in development and reports itself REPAIRED "
                "in production. The real obligation is neither surface: it is the guarantee at "
                "src/core/schemas/_base.py's _accept_only_declared_fields that the field NEVER REACHES THE "
                "IMPLEMENTATION, graded by tests/unit/test_deep_strip.py and "
                "tests/harness/test_forward_compat_acceptance.py. Assert it there and drop this "
                f"declaration.\ndeclared because: {item.why}\n{rejection}"
            )
        elif item.obligation is ErrorCode.INVALID_REQUEST and obliged is ErrorCode.VALIDATION_ERROR:
            problems.append(
                f"{site} is declared malformed({item.kind!r}, obligation=INVALID_REQUEST) but {model.__name__} "
                "ACCEPTS it — the malformation was REPAIRED and the scenario now grades a conformant "
                "payload. Something supplied what the declaration says is wrong: a factory default is "
                "the usual culprit, so express the malformation as a payload() OVERRIDE (assets=OMIT, "
                "format_id=None, ...) rather than relying on the baseline to leave it out.\n"
                f"declared because: {item.why}"
            )
        elif item.obligation is ErrorCode.VALIDATION_ERROR and obliged is ErrorCode.INVALID_REQUEST:
            problems.append(
                f"{site} is declared malformed({item.kind!r}, obligation=VALIDATION_ERROR) but {model.__name__} "
                "REJECTS it — the declaration is MIS-DECLARED. These bytes never reach the seller's rules, so "
                "the buyer receives INVALID_REQUEST and a Then asserting VALIDATION_ERROR cannot pass. Either "
                "the bytes changed, or the obligation was guessed rather than measured; the pin's own reason "
                f"follows.\n{rejection}"
            )
    return problems


def assert_declared_malformations(kwargs: dict[str, Any]) -> None:
    """Fail the scenario if a dispatched item and its declaration disagree with the pin."""
    problems = malformation_problems(kwargs)
    assert not problems, (
        f"{len(problems)} dispatched item(s) disagree with the pinned model about their own "
        "validity. Either the payload is a DEFECT — fix it — or the malformation is deliberate, "
        "in which case declare it at the step that builds it, naming the code the buyer must "
        "receive, measured rather than guessed:\n\n"
        "    from adcp.types import ErrorCode\n"
        "    from tests.factories.malformed import malformed\n"
        "    creative_payload = malformed(\n"
        '        "wrong_type", "<why these exact bytes are the point>", {...},\n'
        "        obligation=ErrorCode.INVALID_REQUEST,   # the pin refuses the bytes themselves\n"
        "    )\n\n" + "\n\n".join(problems)
    )
