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

from src.core.tools.capabilities import get_adcp_capabilities_raw
from src.core.tools.creatives.listing import list_creatives_raw
from src.core.tools.creatives.sync_wrappers import sync_creatives_raw
from src.core.tools.media_buy_delivery import get_media_buy_delivery_raw
from src.core.tools.media_buy_list import get_media_buys_raw
from src.core.tools.products import get_products_raw
from src.core.version_compat import spec_request_model

# (raw function, tool name spec_request_model() resolves to)
RAW_WRAPPERS = (
    (get_products_raw, "get_products"),
    (get_media_buy_delivery_raw, "get_media_buy_delivery"),
    (sync_creatives_raw, "sync_creatives"),
    (list_creatives_raw, "list_creatives"),
    (get_adcp_capabilities_raw, "get_adcp_capabilities"),
    (get_media_buys_raw, "get_media_buys"),
)


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
