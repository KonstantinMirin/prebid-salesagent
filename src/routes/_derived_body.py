"""Generate a REST request body from the DTO and the implementation's signature.

REST is the third place a request shape is written down, and until now it was written by
hand: a ``*Body`` class per route, maintained beside the DTO and the ``_impl`` signature it
is supposed to mirror. That is a drift vector with teeth -- a REST buyer can only send a
field the body declares, so a field missing here is not a validation error, it is a
parameter that silently does nothing. ``ListCreativesBody`` had no ``sort``, and a
spec-shaped REST payload sorted correctly on MCP and A2A and quietly did not on REST.

The body is now DERIVED from the same two artifacts the MCP announcement uses:

    fields = DTO.model_fields  INTERSECT  impl signature

so REST and MCP advertise the same set by construction, and ``e2e_rest`` -- which is real
HTTP against this route, with no schema of its own -- inherits it for free. A2A needs no
schema at all: it consumes the parameter bag wholesale through the request seam.

Version-envelope fields are added back explicitly. They are NOT request data (the DTO
selection strips them by design), but the REST routes read ``adcp_version`` to drive
``apply_version_compat``, so the body must carry them. Naming them here separates envelope
from payload, which the hand-written classes did not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, create_model

from src.core.schema_helpers import accepted_kwargs
from src.core.schemas._base import SalesAgentBaseModel

#: Carried so the route can negotiate, never forwarded as request data.
_ENVELOPE_FIELDS: dict[str, tuple[Any, Any]] = {"adcp_version": (str | None, None)}


def derived_body_model(
    name: str,
    dto: type[BaseModel],
    impl: Callable[..., Any],
    *,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
) -> type[BaseModel]:
    """A request body carrying exactly ``DTO fields INTERSECT impl parameters``.

    ``extra_fields`` is for values the ROUTE needs that are not request data -- keep it
    empty unless a route genuinely reads something the DTO does not describe.
    """
    # ONE definition of "what the impl accepts", shared with the forwarding seam and the MCP
    # derivation, rather than a third independent signature read. It also gets the two cases a
    # bare `set(inspect.signature(impl).parameters)` got wrong: a **kwargs impl (which accepts
    # every field, not the literal name "kwargs") and a patched Mock (which accepts anything,
    # not nothing).
    accepted = accepted_kwargs(impl)
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, field in dto.model_fields.items():
        if accepted is not None and field_name not in accepted:
            continue  # declared by the spec, not implemented here -- so not accepted
        annotation = field.annotation
        fields[field_name] = (annotation if _is_optional(annotation) else annotation | None, None)

    fields.update(_ENVELOPE_FIELDS)
    fields.update(extra_fields or {})
    model = create_model(name, __base__=SalesAgentBaseModel, **fields)
    # Marks the body as DERIVED. The completeness guard asserts hand-written bodies do not
    # LAG their raw wrapper; a derived body deliberately declares LESS -- it drops the
    # wrapper's non-spec parameters, which is the point -- so it is graded by the
    # intersection rule instead.
    model.__derived_from_dto__ = (dto, impl)  # type: ignore[attr-defined]
    return model


def _is_optional(annotation: Any) -> bool:
    return type(None) in getattr(annotation, "__args__", ())
