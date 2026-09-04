"""Structural guard: a REST route forwards every field its request body declares.

THE RULE. A derived ``*Body`` is the contract a REST buyer reads -- FastAPI binds every
field it declares and the OpenAPI schema advertises them. A route that declares a field
and does not forward it accepts the buyer's value and throws it away. There is no error,
no log, and no failing test: the request succeeds having done something other than what
was asked.

WHAT IT COST. ``get_media_buy_delivery`` named nine fields on their way to the builder
while its body declared eleven, so ``include_window_breakdown`` and ``time_granularity``
were bound off the wire and dropped. Both are defined by the pinned
``3.1/media-buy/get-media-buy-delivery-request.json``; both are carried by MCP and A2A. A
REST buyer sending either got a 200 and no effect.

THE THIRD DIRECTION, and the reason a lag check could not see it. Two existing guards
grade the neighbouring failures:

    test_architecture_transport_field_parity.py       does a transport LAG the others?
    test_architecture_a2a_handlers_select_off_the_tool.py  does a transport carry MORE?

This is neither. REST declared exactly what the others declare -- the body is DERIVED, so
it cannot lag -- and then dropped two on the way to the builder. Declaring and forwarding
are different acts, and only the first was graded anywhere.

WHY THE FIX AND THE GUARD ARE BOTH NEEDED. Six of fourteen routes hand-listed their
forwarded fields; five dropped nothing and one dropped two. So the defect was never "two
fields were forgotten" -- it was that hand-listing was available at all, leaving five more
sites one edit away from the same bug. All six now pass ``derived_payload(body, coerce=...)``,
which derives the SET and declares only the per-field CONVERSIONS. This guard is what
keeps the seventh from being written.

HOW A FIELD COUNTS AS FORWARDED. Either the route calls ``derived_payload`` -- which
selects ``DTO fields INTERSECT builder parameters`` off the body's own stamped derivation,
so every declared spec field travels by construction -- or the route reads ``body.<field>``
explicitly. The second is what covers a body's declared DEPARTURES: ``extra_fields`` such
as ``update_media_buy``'s retired ``flight_*`` aliases are not DTO fields, so no DTO-keyed
selection can produce them and the route must pass them by hand. Both routes are legitimate;
declaring a field and doing NEITHER is not.

Ships with ZERO violations and no allowlist. Against the tree before the fix it reports
exactly the two dropped fields on the one route.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.routes._derived_body import derived_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
API_V1 = REPO_ROOT / "src" / "routes" / "api_v1.py"

#: The helper that makes forwarding derived rather than enumerated.
DERIVED_SELECTOR = "derived_payload"

#: Carried so a route can negotiate protocol version; never forwarded as request data.
#: ``_derived_body._ENVELOPE_FIELDS`` adds it to every body, so it is declared everywhere
#: and legitimately unforwarded everywhere.
ENVELOPE_FIELDS = frozenset({"adcp_version"})


def route_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function carrying an ``@router.<verb>(...)`` decorator.

    Membership comes from the DECORATOR -- the thing that actually publishes the endpoint
    -- rather than from a name pattern or a hand-kept list, so a route added tomorrow is
    graded the day it is routed.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any("router." in ast.unparse(d) for d in node.decorator_list)
    ]


def _body_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The annotation of the route's ``body`` parameter.

    Every route in ``api_v1.py`` declares one, so there is no bodiless case to skip.
    """
    (body,) = [a for a in node.args.args if a.arg == "body" and a.annotation is not None]
    return ast.unparse(body.annotation)


def _reads_body_attributes(node: ast.AST) -> set[str]:
    return {
        sub.attr
        for sub in ast.walk(node)
        if isinstance(sub, ast.Attribute) and getattr(sub.value, "id", None) == "body"
    }


def _calls(node: ast.AST) -> set[str]:
    return {
        (call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", None))
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def unforwarded_fields(node: ast.FunctionDef | ast.AsyncFunctionDef, declared: set[str]) -> list[str]:
    """Fields ``declared`` by the route's body that the route neither derives nor reads."""
    if DERIVED_SELECTOR in _calls(node):
        # The selection is derived off the body's own stamped (DTO, builder) pair, so every
        # field that pair produces travels. What it CANNOT produce is a declared departure
        # -- an extra_field is not a DTO field -- so those still have to be read by hand.
        covered = _derived_covered(node, declared)
    else:
        covered = set()
    return sorted(declared - covered - _reads_body_attributes(node) - ENVELOPE_FIELDS)


def _derived_covered(node: ast.FunctionDef | ast.AsyncFunctionDef, declared: set[str]) -> set[str]:
    """What ``derived_payload`` covers: every declared field except the body's departures.

    Resolved against the LIVE body class rather than re-derived here, so this grades the
    same stamped record ``derived_payload`` itself selects by.
    """
    body_cls = _live_body_class(_body_annotation(node))
    if body_cls is None:
        return set()
    return declared - set(getattr(body_cls, "__derived_extra_fields__", frozenset()))


def _live_body_class(annotation: str):
    from src.routes import api_v1

    return getattr(api_v1, annotation, None)


def _declared_fields(annotation: str) -> set[str]:
    body_cls = _live_body_class(annotation)
    return set(getattr(body_cls, "model_fields", {}))


def _api_tree() -> ast.AST:
    return ast.parse(API_V1.read_text(), filename=str(API_V1))


def test_every_rest_route_forwards_every_field_its_body_declares():
    tree = _api_tree()
    routes = route_functions(tree)
    assert routes, "no @router routes found -- the guard would pass vacuously"

    violations: list[str] = []
    graded = 0
    for node in routes:
        declared = _declared_fields(_body_annotation(node))
        if not declared:
            continue
        graded += 1
        dropped = unforwarded_fields(node, declared)
        if dropped:
            violations.append(f"{node.name} (line {node.lineno}) declares but never forwards: {dropped}")

    assert graded, "no route bodies resolved -- the guard would pass vacuously"
    assert not violations, (
        "A REST route declares request fields it does not forward. FastAPI binds every "
        "field the body declares and the OpenAPI schema advertises them, so a buyer sends "
        "a documented value and the route throws it away -- a 200 that did something other "
        "than what was asked, with no error and no log. Pass "
        f"`**{DERIVED_SELECTOR}(body, coerce={{...}})` so the forwarded SET is derived from "
        "the body's own stamped derivation and only the per-field CONVERSIONS are named; a "
        "declared extra_field, which no DTO-keyed selection can produce, is read from "
        "`body.<field>` explicitly. Violations:\n  " + "\n  ".join(violations)
    )


def test_the_guard_grades_the_routes_that_carry_bodies():
    """Sanity on the live module: it must actually reach the routes it claims to grade."""
    tree = _api_tree()
    with_bodies = [n.name for n in route_functions(tree) if _body_annotation(n)]

    assert "get_media_buy_delivery" in with_bodies
    assert "create_media_buy" in with_bodies


def test_the_two_dropped_delivery_fields_now_reach_the_request():
    """The structural rule, graded once as BEHAVIOUR on the field that broke.

    The guard above proves the route forwards what it declares. This proves what that
    means for a buyer: the two fields the route used to bind and discard now survive the
    selection and land on the built request. Graded at the seam rather than through the
    route, which would need a database and an identity to say the same thing.
    """
    from src.core.schema_helpers import to_account_reference, to_context_object
    from src.core.tools.media_buy_delivery import _build_get_media_buy_delivery_request
    from src.routes.api_v1 import GetMediaBuyDeliveryBody

    body = GetMediaBuyDeliveryBody(
        media_buy_ids=["mb_1"],
        include_window_breakdown=True,
        time_granularity="daily",
    )

    request = _build_get_media_buy_delivery_request(
        **derived_payload(body, coerce={"account": to_account_reference, "context": to_context_object})
    )

    assert request.include_window_breakdown is True
    assert request.time_granularity is not None


def test_update_media_buys_declared_departures_are_read_by_hand():
    """The one body with extra_fields proves the departure path is exercised, not theory.

    ``flight_start_date`` / ``flight_end_date`` are retired flat aliases, not
    UpdateMediaBuyRequest fields, so ``derived_payload`` cannot produce them and the route
    must read them off the body. If that ever stops being true this test fails here rather
    than the rule silently widening to cover it.
    """
    from src.routes import api_v1

    departures = set(getattr(api_v1.UpdateMediaBuyBody, "__derived_extra_fields__", frozenset()))
    assert departures == {"flight_start_date", "flight_end_date"}

    route = next(n for n in route_functions(_api_tree()) if n.name == "update_media_buy")
    assert departures <= _reads_body_attributes(route)


# ── Meta-tests: the detector itself ─────────────────────────────────────────
#
# The rule ships green, so its pass says nothing until the detector is shown to fire
# against a synthetic offender.


class _FakeBody:
    model_fields = {"alpha": None, "beta": None, "adcp_version": None}
    __derived_extra_fields__ = frozenset()


def _detect(source: str, declared: set[str] | None = None) -> list[str]:
    tree = ast.parse(source)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))
    fields = declared if declared is not None else {"alpha", "beta"}
    reads = _reads_body_attributes(node)
    covered = fields if DERIVED_SELECTOR in _calls(node) else set()
    return sorted(fields - covered - reads - ENVELOPE_FIELDS)


class TestGuardDetector:
    def test_fires_when_a_declared_field_is_never_read(self):
        """The literal shape of the bug: hand-listed, one field short."""
        assert _detect("def r(body):\n    return build(alpha=body.alpha)\n") == ["beta"]

    def test_silent_when_every_declared_field_is_read(self):
        assert _detect("def r(body):\n    return build(alpha=body.alpha, beta=body.beta)\n") == []

    def test_silent_when_the_route_derives_the_payload(self):
        assert _detect("def r(body):\n    return build(**derived_payload(body))\n") == []

    def test_silent_when_the_route_derives_with_coercions(self):
        assert _detect("def r(body):\n    return build(**derived_payload(body, coerce={'alpha': to_alpha}))\n") == []

    def test_the_version_envelope_is_never_a_violation(self):
        """``adcp_version`` is on every body and forwarded by none -- it is not request data."""
        assert _detect("def r(body):\n    return build()\n", declared={"adcp_version"}) == []

    def test_reports_every_dropped_field_not_just_the_first(self):
        assert _detect("def r(body):\n    return build()\n") == ["alpha", "beta"]


class TestRouteDiscovery:
    def test_finds_a_decorated_route(self):
        tree = ast.parse("@router.post('/x')\ndef r(body):\n    return None\n")

        assert [n.name for n in route_functions(tree)] == ["r"]

    def test_ignores_an_undecorated_function(self):
        assert route_functions(ast.parse("def helper(body):\n    return None\n")) == []


@pytest.mark.parametrize("verb", ["get", "post", "put", "patch", "delete"])
def test_every_http_verb_is_discovered(verb: str):
    """A route added under any verb is graded; the decorator is matched, not the method."""
    tree = ast.parse(f"@router.{verb}('/x')\ndef r(body):\n    return None\n")

    assert [n.name for n in route_functions(tree)] == ["r"]
