"""What an exception tells the operator who has to act on it.

A typed error's ``message`` is a read-only property over ``CODE_TABLE``: a function of
the CODE, not of the raise site, because it is the text that reaches a buyer over the
wire (ADR-010). It cannot say which refusal this was. The operator of the deployment
reads other surfaces (the Admin UI's agent connection test, the result of a media buy
approval), and what an error can tell them is read here, once:

* :func:`operator_cause` is the most specific cause the exception carries;
* :func:`operator_text` is the whole statement: the code, that cause, and the facts the
  error names.

A surface that frames the cause in a sentence of its own calls the first; a surface
that reports the failure as it stands calls the second.
"""

from __future__ import annotations

import json
from typing import Any

from src.core.exceptions import AdCPSalesAgentError, _details_to_wire


def operator_cause(exc: Exception) -> str:
    """The most specific operator-readable cause *exc* carries.

    ``internal_detail`` first. Post-ADR-010 an ``AdCPSalesAgentError``'s
    ``message`` is a read-only property over ``CODE_TABLE`` -- a function of the
    CODE, not of the raise site -- because it is the text that reaches a BUYER
    over the wire, where AdCP 3.1.1 ``transport-errors.mdx`` § Security
    Considerations forbids deployment specifics. So ``message`` reads
    "Configuration error" for a handshake refusal, an egress refusal and an
    unparseable answer alike, and "Service temporarily unavailable" for an
    unreachable endpoint, a rate-limited one and an undelivered request alike.
    The raise sites' own diagnostics moved to ``internal_detail`` for that
    reason, and the surfaces this module serves -- read by the tenant operator
    on their own deployment's admin routes -- are exactly where they belong.

    ``str(exc)`` second. For an ``AdCPSalesAgentError`` that is its ``message``
    (``__str__`` returns the property), so a typed error carrying no detail still
    renders its table sentence. For an UNTYPED exception -- one nothing
    classified, which reaches a caller here because an operator surface reports
    every failure rather than 500ing -- it is the exception's own text, which may
    be third-party. That is deliberate: the reader is an authenticated tenant
    operator, not a buyer whose error responses flow through LLM context, and the
    unanticipated failure is the one where a raw diagnostic is worth the most.

    The type name last, so a cause-less exception (``asyncio.TimeoutError()``
    stringifies to ``""``) renders a sentence rather than a blank one.
    """
    detail = exc.internal_detail if isinstance(exc, AdCPSalesAgentError) else None
    if detail is not None and (text := str(detail).strip()):
        return text
    return str(exc).strip() or type(exc).__name__


def operator_text(exc: Exception) -> str:
    """The whole of what *exc* tells the operator: its code, its cause, and the facts it names.

    For a typed error that is ``CODE: cause (name=value, ...)``. The facts are the slots
    the error's wire projection carries (``Error.from_exception``): ``field``, each set
    field of ``details`` under its wire name, and ``retry_after``, every value as JSON.
    So the operator's sentence and the buyer's envelope state one set of facts, and the
    operator also reads the cause the buyer is not shown. Any other exception is its
    :func:`operator_cause` alone.
    """
    cause = operator_cause(exc)
    if not isinstance(exc, AdCPSalesAgentError):
        return cause
    facts: dict[str, Any] = {
        **({"field": exc.field} if exc.field is not None else {}),
        **(_details_to_wire(exc.details) or {}),
        **({"retry_after": exc.retry_after} if exc.retry_after is not None else {}),
    }
    stated = ", ".join(f"{name}={json.dumps(value)}" for name, value in facts.items())
    return f"{exc.error_code}: {cause}" + (f" ({stated})" if stated else "")
