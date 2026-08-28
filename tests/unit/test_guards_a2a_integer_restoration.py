"""Structural guard for the A2A wire integer-type fix.

Pins two invariants that keep the fix (see
``restore_a2a_integer_types`` in ``src/a2a_server/adcp_a2a_server.py``) from
silently regressing:

1. ``_dict_to_value`` (adcp_a2a_server.py) is the ONLY site in ``src/`` that
   constructs a ``google.protobuf.Struct``/``Value`` for A2A wire data. A
   second, parallel construction site would bypass the integer-restoration
   fix for whatever it builds.
2. Every real ``/a2a`` JSON-RPC route registered on the FastAPI app is
   wrapped with the integer-restoring ASGI wrapper -- a future refactor of
   ``src/app.py``'s route wiring could easily drop the wrapper and silently
   reintroduce the float-widening bug on the real wire.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _struct_value_construction_sites() -> list[str]:
    """Every ``src/`` call to struct_pb2.Value(...) or struct_pb2.Struct(...),
    as ``path:lineno``, found via AST (not regex, so a reformatted call site
    can't slip past)."""
    sites: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            attr_name = func.attr if isinstance(func, ast.Attribute) else None
            if attr_name in {"Value", "Struct"} and isinstance(func, ast.Attribute):
                value_source = func.value
                if isinstance(value_source, ast.Name) and value_source.id == "struct_pb2":
                    sites.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return sites


class TestOnlyOneStructValueConstructionSite:
    def test_dict_to_value_is_the_only_struct_value_construction_site(self):
        sites = _struct_value_construction_sites()
        allowed_file = "src/a2a_server/adcp_a2a_server.py"
        stray = [s for s in sites if not s.startswith(allowed_file)]
        assert not stray, (
            "found a struct_pb2.Value/Struct() construction site outside "
            f"{allowed_file}: {stray}. A2A wire data must be built through "
            "_dict_to_value so integer-typed fields stay covered by "
            "restore_a2a_integer_types -- a parallel "
            "construction site bypasses that fix."
        )
        assert sites, "expected at least the known _dict_to_value construction sites -- scan may be broken"

    def test_scan_would_catch_a_stray_construction_site(self, tmp_path, monkeypatch):
        """Meta-test: prove the AST scan actually detects a stray site, not just
        that today's tree happens to be clean."""
        fake_src = REPO_ROOT / "src" / "_tmp_guard_meta_test_stray.py"
        fake_src.write_text("from google.protobuf import struct_pb2\nv = struct_pb2.Value()\n")
        try:
            sites = _struct_value_construction_sites()
            assert any("_tmp_guard_meta_test_stray.py" in s for s in sites), (
                "the AST scan failed to detect a deliberately-planted stray "
                "struct_pb2.Value() construction site -- the guard is vacuous"
            )
        finally:
            fake_src.unlink()


class TestA2ARoutesWrapWithIntegerRestoration:
    def test_all_a2a_rpc_routes_are_integer_restoration_wrapped(self):
        from src.app import _a2a_rpc_routes

        assert _a2a_rpc_routes, "expected at least one /a2a JSON-RPC route"
        unwrapped = [
            route.path
            for route in _a2a_rpc_routes
            if not getattr(route.endpoint, "__a2a_integer_restoration_wrapped__", False)
        ]
        assert not unwrapped, (
            f"these /a2a routes are missing the integer-restoration wrapper: {unwrapped} -- "
            "the real HTTP wire would silently widen integer fields to floats again"
        )

    def test_unwrapped_route_would_be_caught(self):
        """Meta-test: an endpoint without the marker attribute must fail the check
        above's condition -- proves the guard isn't vacuously true."""

        async def _unmarked_endpoint(request):
            return None

        assert not getattr(_unmarked_endpoint, "__a2a_integer_restoration_wrapped__", False)


class TestIntegerSetMatchesTheSchemas:
    """A2A_WIRE_INTEGER_FIELDS is a hand-maintained set; pin it to the schemas.

    The set drives a NAME-KEYED coercion: any whole-numbered float arriving at one of
    these keys is turned back into an ``int``. That is safe only while every listed name
    really is integer-typed somewhere we control or the spec declares. Nothing checked
    that before -- an 18-name hand-list justified by a prose comment (prkv.5 Lane D D10).
    """

    @staticmethod
    def _pinned_property_types() -> dict[str, set[str]]:
        """property name -> every JSON `type` the pinned 3.1 schemas declare for it."""
        import importlib.util
        import json
        import pathlib

        root = pathlib.Path(importlib.util.find_spec("adcp").origin).parent / "_schemas/3.1"
        types: dict[str, set[str]] = {}

        def walk(node, key=None):
            if isinstance(node, dict):
                declared = node.get("type")
                if key and isinstance(declared, str):
                    types.setdefault(key, set()).add(declared)
                for k, v in node.items():
                    if k == "properties" and isinstance(v, dict):
                        for pk, pv in v.items():
                            walk(pv, pk)
                    else:
                        walk(v, key if k in ("items", "allOf", "anyOf", "oneOf", "$defs", "definitions") else None)
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)

        for f in root.rglob("*.json"):
            try:
                walk(json.loads(f.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        return types

    @staticmethod
    def _app_integer_fields() -> set[str]:
        import inspect

        from pydantic import BaseModel

        import src.core.schemas as app

        out: set[str] = set()
        for name in dir(app):
            obj = getattr(app, name)
            if inspect.isclass(obj) and issubclass(obj, BaseModel):
                for field, info in obj.model_fields.items():
                    annotation = str(info.annotation)
                    if "int" in annotation and "float" not in annotation:
                        out.add(field)
        return out

    def test_every_listed_name_is_integer_typed_somewhere_authoritative(self) -> None:
        """Each name is integer per the PIN or per our own response models (SDK union app).

        Eleven of the eighteen are this server's own count fields (sync/assign counts,
        delivery totals) and correctly do not appear in the pinned schemas at all; they
        are graded against the app models instead. A name in NEITHER place is a name
        nobody can justify, and coercion would be firing on a guess.
        """
        from src.a2a_server.adcp_a2a_server import A2A_WIRE_INTEGER_FIELDS

        pinned = self._pinned_property_types()
        spec_ints = {n for n, ts in pinned.items() if "integer" in ts}
        app_ints = self._app_integer_fields()

        unjustified = sorted(A2A_WIRE_INTEGER_FIELDS - spec_ints - app_ints)
        assert not unjustified, (
            f"A2A_WIRE_INTEGER_FIELDS lists {unjustified}, which no pinned schema and no app "
            f"response model declares as an integer. Coercion fires on those names anyway, so "
            f"either the field is gone or the name is wrong."
        )

    def test_no_new_name_is_ambiguous_between_integer_and_number(self) -> None:
        """A listed name ALSO declared ``number`` in the pin is a coercion hazard.

        The coercion is keyed by NAME, not by the field's own declaration, so where the pin
        declares one property integer and a same-named property elsewhere ``number``, a
        whole-valued float of the SECOND kind gets silently retyped to int -- emitting an
        int where the spec says number. The two below are pre-existing and recorded, not
        endorsed; this only stops the set from growing more of them.
        """
        from src.a2a_server.adcp_a2a_server import A2A_WIRE_INTEGER_FIELDS

        pinned = self._pinned_property_types()
        number_names = {n for n, ts in pinned.items() if "number" in ts}
        known_ambiguous = frozenset({"impressions", "limit"})

        ambiguous = A2A_WIRE_INTEGER_FIELDS & number_names
        new = sorted(ambiguous - known_ambiguous)
        assert not new, (
            f"{new} are listed for int coercion but the pinned schemas also declare them "
            f"`number` somewhere. A whole-valued float at that key would be retyped to int "
            f"on the wire. Narrow the coercion (key it on the response type, not the bare "
            f"name) rather than widening this set."
        )
        stale = sorted(known_ambiguous - ambiguous)
        assert not stale, f"known_ambiguous lists {stale}, no longer ambiguous -- delete the entry"
