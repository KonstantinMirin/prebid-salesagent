#!/usr/bin/env python3
"""Structural guard: no harness env may silently drop a field from the REST body.

``build_rest_body`` turns a test's kwargs into the JSON body of the REST leg. When it drops a kwarg
it does not recognise, the request still goes out — and because every field of an AdCP request
schema is optional, the route answers 200 to the reduced body. The test then asserts against a
response to a payload it never sent. A parametrized ``[a2a, rest]`` test written that way reads as
cross-transport coverage while grading one transport (#1600).

It also made REST error-path tests impossible to write: a malformed value cannot be expressed
through a typed ``req=`` model, because the model rejects it client-side before it can be sent. So
the only way to drive a bad payload through the real route is raw kwargs — which were exactly what
got dropped. That is why the get_signals operation-label parity test (#1600) had to stay A2A-only.

The rule is executable, not structural: hand every env a canary field and require it on the wire.
That catches a re-implemented field-allowlist builder, a ``return {}`` fallback, and any future
shape nobody has thought of yet — none of which a source-text scan could distinguish from the
legitimate serialization overrides these classes are entitled to have.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

pytestmark = pytest.mark.architecture

CANARY_FIELD = "__canary_unknown_field__"
CANARY_VALUE = "canary"


def _rest_capable_envs() -> list[type]:
    """Every harness env class that declares a REST endpoint, discovered — never hand-listed."""
    import tests.harness as harness_pkg
    from tests.harness._base import BaseTestEnv

    found: dict[str, type] = {}
    for module_info in pkgutil.iter_modules(harness_pkg.__path__):
        module = importlib.import_module(f"tests.harness.{module_info.name}")
        for obj in vars(module).values():
            if not (inspect.isclass(obj) and issubclass(obj, BaseTestEnv) and obj is not BaseTestEnv):
                continue
            endpoint = inspect.getattr_static(obj, "REST_ENDPOINT", None)
            if isinstance(endpoint, str) and endpoint:
                found[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return [found[key] for key in sorted(found)]


def _carries_a_body(env_cls: type) -> bool:
    """GET routes have no request body — for them the correct behavior is to refuse, not to drop."""
    return str(inspect.getattr_static(env_cls, "REST_METHOD", "post")).lower() != "get"


BODY_ENVS = [cls for cls in _rest_capable_envs() if _carries_a_body(cls)]
GET_ENVS = [cls for cls in _rest_capable_envs() if not _carries_a_body(cls)]


def test_discovery_finds_the_rest_envs():
    """If discovery silently returns nothing, every case below vacuously passes."""
    envs = _rest_capable_envs()
    assert len(envs) >= 8, f"Only found {len(envs)} REST-capable envs — discovery is broken: {envs}"
    assert BODY_ENVS, "No body-carrying REST env discovered — the parametrized cases grade nothing."


@pytest.mark.parametrize("env_cls", GET_ENVS, ids=lambda c: c.__name__)
def test_get_route_envs_refuse_fields_instead_of_dropping_them(env_cls: type):
    """A GET route cannot carry a body, so handing it fields must fail rather than no-op."""
    env = env_cls.__new__(env_cls)

    with pytest.raises(AssertionError, match="no request body|cannot go on this wire"):
        env_cls.build_rest_body(env, **{CANARY_FIELD: CANARY_VALUE})


@pytest.mark.parametrize("env_cls", BODY_ENVS, ids=lambda c: c.__name__)
def test_build_rest_body_does_not_drop_unknown_fields(env_cls: type):
    """A field the caller supplied must appear in the body, whatever the env does with the rest."""
    env = env_cls.__new__(env_cls)  # no __init__: build_rest_body must be a pure function of kwargs

    body = env_cls.build_rest_body(env, **{CANARY_FIELD: CANARY_VALUE})

    assert body.get(CANARY_FIELD) == CANARY_VALUE, (
        f"{env_cls.__name__}.build_rest_body() dropped {CANARY_FIELD!r} — it returned {body!r}.\n"
        f"A dropped field does not fail: the request goes out reduced, the route returns 200 because "
        f"the schema's fields are all optional, and the REST leg grades a payload it never sent.\n"
        f"Handle the fields needing special serialization and delegate the rest to "
        f"super().build_rest_body(**kwargs) — never return a dict built only from a hardcoded field "
        f"list, and never return {{}} for kwargs you do not recognise."
    )


@pytest.mark.parametrize("env_cls", BODY_ENVS, ids=lambda c: c.__name__)
def test_build_rest_body_preserves_malformed_values(env_cls: type):
    """A malformed value must reach the wire unchanged — that is the point of a REST error test.

    If the harness coerces or validates on the way out, the route never sees the bad payload and the
    error path under test is never exercised.
    """
    env = env_cls.__new__(env_cls)
    malformed = ["not-an-object", {"unexpected": None}, 12345]

    body = env_cls.build_rest_body(env, **{CANARY_FIELD: malformed})

    assert body.get(CANARY_FIELD) == malformed, (
        f"{env_cls.__name__}.build_rest_body() altered a malformed value: sent {malformed!r}, "
        f"body has {body.get(CANARY_FIELD)!r}. The harness must not validate on the caller's behalf."
    )


def test_empty_kwargs_still_yields_an_empty_body():
    """The one legitimate empty body: the caller genuinely sent no fields."""
    from tests.harness.signals import SignalsEnv

    env = SignalsEnv.__new__(SignalsEnv)
    assert SignalsEnv.build_rest_body(env) == {}
