"""Grades :func:`src.core.schemas.conformance.omit_declared`.

Three checks, and deliberately no fourth. Nothing consumes the decorator yet, so there is
no behaviour here to grade end to end; the correctness that matters is graded as a
consequence at salesagent-prkv.106.7.1, where a buyer sending an omitted field is rejected
on all three transports. These three cover what the decorator itself promises: a correct
table works against a REAL SDK model, an omitted field is rejected AT VALIDATION, and a
stale name refuses to import.
"""

import pytest
from adcp.types import GetProductsRequest as LibraryGetProductsRequest
from pydantic import ConfigDict, ValidationError

from src.core.schemas import conformance
from src.core.schemas.conformance import omit_declared

#: A field ``get_products-request.json`` declares, that the decorator omits in these checks,
#: and a payload the SPEC model accepts in full. Rejection of the payload can then only come
#: from the omission — not from the field's own type, and not from a missing required one.
OMITTED_FIELD = "if_pricing_version"
PAYLOAD = {"buying_mode": "brief", OMITTED_FIELD: "2.4"}


def _narrowed_subclass() -> type[LibraryGetProductsRequest]:
    """An UNDECORATED subclass of the real SDK request model, strict about extras.

    Built per test rather than at module scope because ``omit_declared`` mutates the class
    it is handed; a shared class would carry one test's omission into the next.
    """

    class NarrowedGetProductsRequest(LibraryGetProductsRequest):
        model_config = ConfigDict(extra="forbid")

    return NarrowedGetProductsRequest


def test_correct_table_does_not_raise_against_a_real_sdk_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row naming a field the spec model DOES declare decorates cleanly.

    Asserted against the real ``adcp`` model, never a synthetic stand-in: the whole premise
    of the table is that it names fields of the pinned SDK's shape, so a check that invents
    its own parent grades nothing about the pin. The spec model itself must come out
    untouched — the narrowing belongs to the subclass, and the SDK type is shared.
    """
    cls = _narrowed_subclass()
    monkeypatch.setattr(conformance, "OMITTED", {cls.__name__: {OMITTED_FIELD: "not implemented"}})

    assert omit_declared(cls) is cls
    assert OMITTED_FIELD not in cls.model_fields
    assert OMITTED_FIELD in LibraryGetProductsRequest.model_fields


def test_omitted_field_is_rejected_at_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent from ``model_fields`` is not the claim. REJECTED by the validator is.

    The two diverge, and the divergence is what ``model_rebuild(force=True)`` closes.
    Measured at pydantic 2.12.5 / adcp 6.6.0: an SDK request subclass DEFERS its core
    schema (``MockValSer`` at class creation), so at decoration time a pop happens to be
    seen by a validator that has not been compiled yet — and a decorator missing the rebuild
    would pass this check for the wrong reason. The ``model_rebuild()`` below compiles it
    first, which is the state any already-used class is in. Without the force-rebuild in the
    decorator, this payload is then ACCEPTED and ``if_pricing_version`` is set on the
    instance while ``model_fields`` reports it gone.
    """
    cls = _narrowed_subclass()
    cls.model_rebuild()
    assert cls.model_validate(PAYLOAD).if_pricing_version == "2.4", "the SPEC shape accepts this payload"

    monkeypatch.setattr(conformance, "OMITTED", {cls.__name__: {OMITTED_FIELD: "not implemented"}})
    omit_declared(cls)

    with pytest.raises(ValidationError) as raised:
        cls.model_validate(PAYLOAD)
    assert [(e["type"], e["loc"]) for e in raised.value.errors()] == [("extra_forbidden", (OMITTED_FIELD,))]


def test_a_stale_name_raises_and_names_the_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """A name that omitted nothing is a name the spec model does not declare.

    A typo and a field an SDK bump removed are the same failure, and it is raised at
    decoration time so the application never starts on a wrong table. The message must name
    the offending field — that is the whole diagnostic.
    """
    cls = _narrowed_subclass()
    monkeypatch.setattr(conformance, "OMITTED", {cls.__name__: {"if_pricing_versoin": "typo"}})

    with pytest.raises(ValueError, match=r"cannot omit \['if_pricing_versoin'\]"):
        omit_declared(cls)
