"""``derived_payload`` SELECTS. It must not transform, and it must not lose nested content.

WHY THIS FILE EXISTS, stated plainly because the previous check was mine and it passed.
Converting the REST routes to ``derived_payload`` shipped a security regression: a package's
``creative_ids`` stopped reaching the request, so ``create_media_buy`` had no creative
reference left to validate and accepted cross-principal references it must reject. Ten
integration tests and seven BDD scenarios failed, all of them create_media_buy failing to
REJECT something.

The cause was one line. ``select_request_fields`` DUMPS a BaseModel source, and
``model_dump()`` applies ``exclude=True`` all the way down -- so
``PackageRequest.creative_ids``, marked internal to keep it out of RESPONSES, was deleted
from the buyer's REQUEST. A serialization marker silently became a request-selection
decision for nested models, which nobody decided.

THE CHECK THAT MISSED IT, and the lesson. I compared old and new construction by building
each request BOTH ways from ONE representative body and diffing ``model_dump()``. That is
sound for the body it used, and it cannot see a field the sample did not carry -- and the
sample carried no creative reference inside ``packages[]``. It was a check over a SAMPLE
where the rule needed a check over the POPULATION, which is the same error, in the same
week, that produced a schema count of six that was seven and a "zero conflicts" that was
two. A sample is always shorter than the rule, and always shorter in the direction of what
its author already believes.

So this grades the INVARIANT instead of a comparison: for every field it selects,
``derived_payload`` returns the body's value UNCHANGED. Identity, not equality --
``is``, so a dump, a copy, or any coercion of a nested model fails here rather than in
production. A rule stated that way cannot be satisfied by a lucky sample, because it does
not depend on which fields the sample happens to carry.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.routes._derived_body import derived_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
API_V1 = REPO_ROOT / "src" / "routes" / "api_v1.py"


def _body_classes() -> dict[str, type]:
    """Every derived ``*Body`` a route actually binds, read off the route signatures."""
    from src.routes import api_v1

    tree = ast.parse(API_V1.read_text(), filename=str(API_V1))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not any("router." in ast.unparse(d) for d in node.decorator_list):
            continue
        for arg in node.args.args:
            if arg.arg == "body" and arg.annotation is not None:
                names.add(ast.unparse(arg.annotation))
    return {n: getattr(api_v1, n) for n in sorted(names) if getattr(api_v1, n, None) is not None}


#: A package carrying the nested reference that was being lost. ``creative_ids`` is
#: ``exclude=True`` on PackageRequest -- internal for serialization, buyer input on the way
#: in -- which is exactly the combination a dump destroys.
_PACKAGE_WITH_A_CREATIVE_REFERENCE = {
    "product_id": "prod_1",
    "pricing_option_id": "po_1",
    "budget": 1000.0,
    "creative_ids": ["cr_1"],
}

_IDEMPOTENCY_KEY = "idem-" + "x" * 20


def _populated_create_media_buy_body():
    from src.routes.api_v1 import CreateMediaBuyBody

    return CreateMediaBuyBody(
        brand={"domain": "acme.com"},
        packages=[_PACKAGE_WITH_A_CREATIVE_REFERENCE],
        start_time="2026-02-01T00:00:00Z",
        end_time="2026-02-28T00:00:00Z",
        account={"account_id": "a1"},
        idempotency_key=_IDEMPOTENCY_KEY,
        po_number="po-1",
    )


def test_a_packages_creative_reference_reaches_the_built_request():
    """The regression, graded where a buyer would feel it.

    A package referencing a creative must arrive with that reference intact. Without it
    create_media_buy has nothing to validate and accepts references it must refuse --
    including another principal's, which is the security failure this file is named for.
    """
    from src.core.schema_helpers import (
        to_account_reference,
        to_brand_reference,
        to_context_object,
        to_push_notification_config,
        to_reporting_webhook,
    )
    from src.core.tools.media_buy_create import _build_create_media_buy_request

    request = _build_create_media_buy_request(
        **derived_payload(
            _populated_create_media_buy_body(),
            coerce={
                "account": to_account_reference,
                "brand": to_brand_reference,
                "reporting_webhook": to_reporting_webhook,
                "push_notification_config": to_push_notification_config,
                "context": to_context_object,
            },
        )
    )

    assert request.packages[0].creative_ids == ["cr_1"]


def test_derived_payload_returns_the_bodys_values_unchanged():
    """The INVARIANT, on a populated body: every selected value is the body's own object.

    ``is`` rather than ``==``. A dump compares equal for scalars and would hide exactly the
    failure that shipped -- the nested model surviving as a lossy dict. Identity is what
    makes "selects, does not transform" a testable claim.
    """
    body = _populated_create_media_buy_body()

    payload = derived_payload(body)

    assert payload, "nothing was selected -- the check would be vacuous"
    for name, value in payload.items():
        # `is`, NOT `==`. Do not "simplify" this to equality: a model_dump() of a nested
        # model compares EQUAL to the model for every scalar it kept, so `==` passes on
        # exactly the bug this file exists for -- a package arriving as a dict that quietly
        # lost its exclude=True creative_ids. Identity is the only form of this assertion
        # that can fail on a lossy rebuild.
        assert value is getattr(body, name), (
            f"derived_payload transformed {name!r}: it must SELECT the body's value, not "
            f"rebuild it. A dump here deletes nested exclude=True fields from the buyer's "
            f"request."
        )


def test_coercions_touch_only_the_fields_they_name():
    """A field named in ``coerce`` may be converted; nothing else may be.

    ``account`` is not asserted to CHANGE: FastAPI has already bound it to the typed model,
    and ``to_account_reference`` short-circuits on an instance, so the converter is
    idempotent here and returns the same object. What matters is the other direction --
    that naming one field does not quietly rebuild the rest.
    """
    from src.core.schema_helpers import to_account_reference

    body = _populated_create_media_buy_body()

    payload = derived_payload(body, coerce={"account": to_account_reference})

    for name, value in payload.items():
        if name == "account":
            continue
        assert value is getattr(body, name), f"{name!r} was transformed without being named in coerce"


def test_a_coercion_runs_when_conversion_is_actually_needed():
    """The converter is wired, not merely tolerated: a raw dict comes back typed."""
    from adcp.types import AccountReference

    from src.core.schema_helpers import to_account_reference
    from src.routes.api_v1 import CreateMediaBuyBody

    body = CreateMediaBuyBody.model_construct(account={"account_id": "a1"})

    payload = derived_payload(body, coerce={"account": to_account_reference})

    assert isinstance(payload["account"], AccountReference)


@pytest.mark.parametrize("body_name", sorted(_body_classes()))
def test_no_route_body_loses_a_field_it_carries(body_name: str):
    """Across EVERY route body, not one sample: a value the body holds is a value selected.

    Populated by asking each body for the fields it declares rather than by a fixture, so a
    field added tomorrow is covered without editing this test -- which is the property the
    check this replaces did not have.
    """
    body_cls = _body_classes()[body_name]
    declared = {name for name, f in body_cls.model_fields.items() if not f.is_required()}
    assert declared or body_cls.model_fields, f"{body_name} declares nothing to grade"

    derivation = getattr(body_cls, "__derived_from_dto__", None)
    assert derivation is not None, f"{body_name} is not a derived body"
    dto, impl = derivation

    from src.core.schema_helpers import accepted_kwargs

    accepted = accepted_kwargs(impl)
    # The version envelope is carried by every derived body so a route can negotiate on it,
    # and stripped by the selector by design -- it is not request data. Excluding it here
    # keeps the test grading the rule rather than re-litigating that decision.
    from src.core.schema_helpers import _VERSION_ENVELOPE_FIELDS

    selectable = {
        name
        for name, f in dto.model_fields.items()
        if not f.exclude
        and name in body_cls.model_fields
        and name not in _VERSION_ENVELOPE_FIELDS
        and (accepted is None or name in accepted)
    }

    # Build with model_construct so every declared field can be present without satisfying
    # each one's validators -- the question here is selection, not validation.
    sentinels = {name: object() for name in selectable}
    body = body_cls.model_construct(**sentinels)

    payload = derived_payload(body)

    missing = sorted(name for name in sentinels if name not in payload)
    assert not missing, f"{body_name}: derived_payload dropped {missing}"
    for name, sentinel in sentinels.items():
        # `is` again, and for the same reason as above -- equality would accept a rebuild.
        assert payload[name] is sentinel, f"{body_name}: {name!r} came back transformed"
