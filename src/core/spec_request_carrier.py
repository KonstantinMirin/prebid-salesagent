"""Tool-side consumption of the acceptance seam's carrier.

`accepts_spec_request_fields` (src/core/version_compat.py) is the seam every
transport crosses: it builds the wire request as the tool's pinned model and
delivers it to the tool as `_spec_request`. DELIVERY IS NOT DISPOSITION. A tool
that receives the carrier and never reads it still DROPS the buyer's field --
one frame further in than the transport argument-binder the seam moved it from,
and just as silent.

These two helpers are the tool-side half of the two-way rule, and they live in
one module so the next tool cannot invent a third, quieter answer:

    HONOR  -- `merge_spec_request` fills every field the flat wrapper path left
              unset from the carrier, DERIVED from the request model rather than
              named field by field. Naming them is the same hand-list disease as
              naming them at a transport; `account`, `invoice_recipient`,
              `new_packages` and `revision` all reached the seam and stopped at
              a hand-list for exactly that reason.
    REFUSE -- `refuse_unsupported_fields` raises when the buyer ASSERTED a field
              this seller cannot act on. AdCP 3.1.1's own error enum classifies
              `UNSUPPORTED_FEATURE` as correctable with the recovery "check
              get_adcp_capabilities and remove unsupported fields", which is
              exactly this situation: the field is spec-defined and legitimately
              sent, and this seller does not implement it.

`refuse_unsupported_fields` reads the REQUEST MODEL, not raw kwargs, so it fires
on every call path into `_impl` -- MCP, A2A, REST and direct calls alike -- and
so the refusal is transport-agnostic (Critical Pattern #5).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from src.core.exceptions import AdCPCapabilityNotSupportedError


def merge_spec_request[RequestT: BaseModel](req: RequestT, spec_request: BaseModel | None) -> RequestT:
    """Fill every field the flat wrapper path left unset from the seam's carrier.

    DERIVED over `type(req).model_fields`, never a field list: a spec bump widens
    this automatically, and a field added to the pinned model cannot be forgotten
    here the way a hand-written copy loop forgets it.

    The flat path WINS where it set a value -- those arguments are already coerced
    objects the transport bound (``AccountReference``, ``BrandReference``,
    ``PushNotificationConfig``), while the carrier is built from raw wire.

    `spec_request` is None on every call path that predates the seam (direct
    `_impl` tests, the harness), so this is a no-op there rather than a new
    required argument.
    """
    if spec_request is None:
        return req
    if not isinstance(req, BaseModel):
        # Nothing to merge INTO. Production always hands `_impl` a typed request
        # model, but unit tests legitimately pass a mock, and a mock has no
        # `model_fields` to iterate. Returning it untouched keeps this helper's
        # contract explicit ("operates on a Pydantic request model") instead of
        # raising AttributeError from deep inside the merge loop.
        return req
    for name in type(req).model_fields:
        if getattr(req, name, None) is not None:
            continue
        value = getattr(spec_request, name, None)
        if value is not None:
            setattr(req, name, value)
    return req


def _is_asserted(req: BaseModel, name: str, value: Any) -> bool:
    """Did the buyer actually ASSERT this field, or just restate its default?

    `include_purged: false` on a seller that never returns tombstones asks for
    exactly what it already gets -- refusing it would reject a request nothing
    was dropped from. Only a value that DIFFERS from the field's own default
    represents a buyer expectation this seller cannot meet.
    """
    if value is None:
        return False
    model_fields = getattr(type(req), "model_fields", None)
    if model_fields is None:
        # Not a Pydantic model (a mocked request in a unit test). Whether the
        # buyer "asserted" a field is undefined without the field's own default,
        # so this cannot be judged — and refusing on an unjudgeable value would
        # reject requests for a reason the buyer cannot act on.
        return False
    field = model_fields.get(name)
    if field is None:
        return True
    return bool(value != field.get_default(call_default_factory=True))


def refuse_unsupported_fields(req: BaseModel, *, tool: str, unsupported: Mapping[str, str]) -> None:
    """Refuse, loudly, the body-semantic fields *tool* accepts but cannot act on.

    Args:
        req: The request model `_impl` is about to act on, carrier already merged.
        tool: The AdCP task name, for the buyer-facing message.
        unsupported: field name -> why this seller cannot act on it. The names are
            spelled out here (not derived) because "what this seller implements"
            is per-field knowledge that exists nowhere else -- and spelling them
            out is what makes the field's disposition readable in the code that
            owes it, which `test_architecture_spec_field_disposition.py` grades.

    Raises:
        AdCPCapabilityNotSupportedError: when at least one field is asserted.
    """
    if not isinstance(req, BaseModel):
        # Production always hands `_impl` a typed request model. A unit test that
        # mocks the request cannot be judged here: `enum_value`-style helpers
        # deliberately stringify a mock's `.value`, so every field would look like
        # a buyer assertion and be REFUSED — turning mocked tests into spurious
        # capability rejections. Refusing requires a real model to read defaults
        # from, so a non-model refuses nothing.
        return
    asserted = [(name, why) for name, why in unsupported.items() if _is_asserted(req, name, getattr(req, name, None))]
    if not asserted:
        return
    names = ", ".join(name for name, _ in asserted)
    detail = "; ".join(f"{name}: {why}" for name, why in asserted)
    raise AdCPCapabilityNotSupportedError(
        f"{tool} does not support {names} ({detail})",
        suggestion=(
            f"Remove {names} from the request and resend. Call get_adcp_capabilities to see what this seller supports."
        ),
    )
