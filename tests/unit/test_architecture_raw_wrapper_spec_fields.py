"""Guard: A2A/REST `_raw()` wrappers accept every field their pinned request
schema defines, the same as MCP (GH #1193, salesagent-g6m2.10).

`accepts_spec_request_fields` (src/core/version_compat.py) was originally
applied only at the MCP registration chokepoint (src/core/main.py:351). The
sibling `_raw()` functions in src/core/tools/ — the ones A2A and REST call
directly — never got the same treatment, so calling one of them with a
spec-defined keyword its own signature omitted raised a plain Python
`TypeError` at argument-binding time, no DB or transport required to
reproduce (confirmed live: `get_products_raw(ext=...)` raised
"unexpected keyword argument 'ext'").

The fix generalizes the SAME decorator (same field-set source,
`spec_request_model()`) onto the `_raw()` functions directly — the decorator
resolves the tool name by stripping a trailing `_raw`, so one mechanism
covers both the MCP registration path and the raw-wrapper call sites. This
mirrors the already-sanctioned "accept the field, don't yet honor it"
posture MCP tools carry today (salesagent-vuz9t.6/.14): the raw wrapper
becomes callable with the full field set; nothing downstream (including
today's A2A skill-handler dispatch, which still hand-extracts a narrow named
subset from the wire `parameters` dict) forwards or acts on the newly
accepted fields yet. That gap — A2A's dispatch not yet wiring these fields
through to the raw functions — is out of scope here, tracked per-field
elsewhere.

Scope: exactly the 6 individually-typed `_raw()` functions the disease scan
on salesagent-g6m2.10 found missing spec fields. `create_media_buy_raw` /
`update_media_buy_raw` already declared `ext` by hand before this bug and
were left untouched (narrower, deliberate scope per the task's routing
decision — not part of this fix). req-object-based `_raw()` functions
(list_accounts_raw, sync_accounts_raw, list_creative_formats_raw,
get_signals_raw) are immune by construction: whatever fields the caller
puts on the `req` object ride through, including any the model defines.

This is a signature-shape guard rather than a behavioral test on purpose —
same rationale as test_architecture_spec_request_fields.py: it covers all 6
functions without 6 DB fixtures. The paired behavioral proof (a real call
into a raw function with previously-rejected fields, live DB) is
tests/integration/test_raw_wrapper_spec_fields_accepted.py.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.version_compat import spec_request_model


# Seam membership is DERIVED, never hand-listed (Lane A / S2). A literal tuple
# is a second place to keep in sync, and a 16th `_raw()` that forgets to appear
# in it rejoins the seam in name only — silently, with this guard still green.
#
# Every `_raw()` under src/core/tools/ must satisfy EXACTLY ONE arm:
#   (a) it carries @accepts_spec_request_fields, or
#   (b) it is req-object-based, so whatever the caller puts on `req` rides
#       through and no per-field acceptance exists to get wrong, or
#   (c) spec_request_model() resolves None — a non-spec surface with no pinned
#       fields to accept.
# Arms (b) and (c) are PREDICATES evaluated here, not name lists, so a new raw
# function is classified by what it IS rather than by remembering to add it.
def _all_raw_wrappers() -> list[tuple[str, object]]:
    """Every `*_raw` callable defined under src/core/tools/, found by import."""
    import importlib
    import pkgutil

    import src.core.tools as tools_pkg

    found: dict[str, object] = {}
    for mod in pkgutil.walk_packages(tools_pkg.__path__, prefix="src.core.tools."):
        try:
            module = importlib.import_module(mod.name)
        except Exception:  # a module that cannot import is another guard's problem
            continue
        for attr in dir(module):
            if attr.endswith("_raw") and callable(getattr(module, attr, None)):
                found.setdefault(attr, getattr(module, attr))
    return sorted(found.items())


def _is_req_object_based(fn) -> bool:
    """Arm (b): the wrapper takes a `req` model rather than flat spec fields."""
    inner = inspect.unwrap(fn)
    return "req" in inspect.signature(inner).parameters


def _seam_members() -> list[tuple[object, str]]:
    """Arm (a) members: the raw wrappers that must carry the decorator."""
    members = []
    for name, fn in _all_raw_wrappers():
        tool_name = name.removesuffix("_raw")
        if spec_request_model(tool_name) is None:  # arm (c)
            continue
        if _is_req_object_based(fn):  # arm (b)
            continue
        members.append((fn, tool_name))
    return members


RAW_WRAPPERS = tuple(_seam_members())


@pytest.mark.parametrize("raw_fn,tool_name", RAW_WRAPPERS, ids=lambda x: getattr(x, "__name__", x))
def test_raw_wrapper_accepts_every_field_its_request_schema_defines(raw_fn, tool_name: str):
    """A _raw() wrapper may not reject a field the pinned spec declares."""
    model = spec_request_model(tool_name)
    assert model is not None, f"{tool_name} has no SDK request model at the pin — remove it from RAW_WRAPPERS"

    accepted = set(inspect.signature(raw_fn).parameters)
    missing = sorted(set(model.model_fields) - accepted)

    assert not missing, (
        f"{raw_fn.__name__} rejects {len(missing)} field(s) that {model.__name__} declares: {missing}. "
        "A direct call with one of these keywords raises TypeError at argument-binding time — "
        "apply @accepts_spec_request_fields to this function (salesagent-g6m2.10)."
    )


def test_raw_wrapper_derives_from_the_same_decorator_mcp_uses():
    """The raw-wrapper field set is DERIVED, not hand-listed, per the AC.

    Every wrapper in RAW_WRAPPERS must actually be the decorated function
    (functools.wraps sets __wrapped__) — proves the fix reused
    accepts_spec_request_fields rather than manually adding parameters one
    signature at a time, so a spec bump (or a 7th raw function) can't
    silently reopen this gap.
    """
    undecorated = [raw_fn.__name__ for raw_fn, _ in RAW_WRAPPERS if getattr(raw_fn, "__wrapped__", None) is None]
    assert not undecorated, (
        f"{undecorated} are not decorated with @accepts_spec_request_fields — "
        "hand-listing parameters instead of deriving them from spec_request_model() "
        "is exactly the anti-pattern this guard exists to prevent."
    )
