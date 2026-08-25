"""Declared shapes for every error ``details`` block.

An error's ``details`` is a class instance, never a dict. That is the whole
point of this module: a field is named once, in a class declaration, so
``version`` at one raise site and ``revision`` at another is a typecheck
failure rather than two different keys on the buyer's wire. Before this,
``AdCPValidationError`` alone carried 30 distinct key sets across 34 sites,
with ``validation_errors``, ``creative_errors``, ``config_errors``,
``adapter_errors`` and ``violations`` all naming "a list of problems".

Each subclass names the code it belongs to via ``_code``. That single
declaration does three jobs:

* ``AdCPError.__init_subclass__`` asserts an exception class and its detail
  class agree about the code, at import time.
* ``Error.from_details()`` reads the code off the instance, so the advisory
  lane needs no code argument and cannot pair a code with a foreign shape.
* The exception class ADOPTS it, so ``_code`` is declared once per error and a
  disagreement between the two halves cannot be written down.

Extras are declared, not accepted. ``get_pydantic_extra_mode()`` yields
``forbid`` in development and CI and ``ignore`` in production, so an undeclared
key is a test failure locally and silently dropped in production. A field a
call site wants is added here. The pin's ``additionalProperties: true`` says
the wire tolerates extras; it does not oblige this seller to accept undeclared
ones at construction.

Two shapes clamp to ``forbid`` unconditionally, because the pin clamps them:
``agent-permission-denied`` and ``billing-not-permitted-for-agent``. Their
``additionalProperties: false`` is a cross-tenant onboarding oracle clamp —
full disclosure of an agent's commercial state in a single probe is what it
prevents — so it holds in production too.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from src.core.config import get_pydantic_extra_mode
from src.core.errors.codes import CODE_TABLE, ErrorCode, ErrorCodeT

__all__ = ["ErrorDetails", "ErrorProblem", "VersionUnsupportedDetails"]


class ErrorDetails(BaseModel):
    """Base for every error-details shape.

    ``_code`` is annotation-only here, so ``hasattr`` is False on the base and
    True on every subclass that declares one. A subclass that names a code the
    table does not classify fails at class creation rather than at first raise,
    mirroring the check ``AdCPError.__init_subclass__`` already performs.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    _code: ClassVar[ErrorCodeT]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        code = cls.__dict__.get("_code")
        if code is not None and code not in CODE_TABLE:
            raise TypeError(
                f"{cls.__name__} declares _code {code!r}, which CODE_TABLE does not "
                "classify. Declare a code the table knows, or add the entry."
            )

    def to_wire(self) -> dict[str, Any]:
        """Serialize for the ``details`` slot of the wire error object.

        Unset fields are omitted rather than emitted as nulls: a details block
        is a bag of specifics, and a null specific is noise the buyer has to
        filter. ``exclude_none`` also keeps a class with many optional fields
        from widening every envelope that uses one of them.

        ``mode="json"`` because the destination is a wire slot, not a Python
        caller: a nested ``ErrorProblem.code`` is a ``StrEnum`` member, and
        while that happens to be JSON-safe by inheritance, a future date or
        UUID field on any detail class would not be.
        """
        return self.model_dump(mode="json", exclude_none=True)


class ErrorProblem(BaseModel):
    """One problem inside a ``problems`` list. Carries facts, never a sentence.

    This replaces five key names that were all the same concept:
    ``validation_errors``, ``creative_errors``, ``config_errors``,
    ``adapter_errors`` and ``violations``. Every one held ``list[str]``, and
    every string was built by interpolating structured facts into an f-string
    and discarding the structure — ``f"{r.creative_id}: {err.message}"``,
    ``f"Creative {cid} has format '{fmt}' which is not accepted by product
    {pid} (accepted formats: {sorted(accepted)})"``. The key name smuggled
    provenance no buyer could read, and the buyer had to parse prose to learn
    which creative failed.

    There is NO free-text field here, deliberately. A declared class stops
    field-name drift but not prose inside a declared field, so a ``reason: str``
    slot would just relocate the f-string one level down.

    ``code`` classifies the problem using the SAME vocabulary as the error that
    carries it, rather than a parallel ``reason`` enum. That keeps one code
    table for one job, and it means the buyer can render a sentence from
    ``CODE_TABLE`` for each problem exactly as they do for the error itself —
    which is the epic's invariant applied one level down.

    ``rejected_value`` and ``accepted_values`` are the pin's canonical
    rejection-set keys (v3.1.1 ``core/error.json``, the ``details``
    description): "sellers SHOULD use the canonical key ``accepted_values``
    rather than seller-specific variants observed in the wild". Using them lets
    a buyer's error classifier read this without per-seller pattern matching.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    code: ErrorCodeT | None = None
    subject_type: Literal["creative", "product", "package", "account"] | None = None
    subject_id: str | None = None
    field: str | None = None
    rejected_value: str | None = None
    accepted_values: list[str] | None = None


# ---------------------------------------------------------------------------
# Pinned shapes. Each mirrors its file under the pinned schema bundle at
# dist/schemas/3.1.1/error-details/, field for field, plus any extra the pin
# permits and a call site actually needs. A field the pin marks required is
# required here.
# ---------------------------------------------------------------------------


class VersionUnsupportedDetails(ErrorDetails):
    """``VERSION_UNSUPPORTED`` — v3.1.1 ``error-details/version-unsupported.json``.

    ``supported_versions`` is the pin's only required field. ``build_version``
    is advisory only: the schema states buyers MUST NOT negotiate on it, so it
    rides here as a triage aid rather than as negotiation input.

    ``adcp_version`` and ``adcp_major_version`` echo what the caller asked for.
    The pin leaves this shape ``additionalProperties: true``, so both are legal
    on the wire; declaring them is what stops the next site spelling one of
    them ``version`` or ``major``.
    """

    _code: ClassVar[ErrorCodeT] = ErrorCode.VERSION_UNSUPPORTED

    supported_versions: list[str]
    supported_majors: list[int] | None = None
    build_version: str | None = None
    adcp_version: str | None = None
    adcp_major_version: int | None = None
