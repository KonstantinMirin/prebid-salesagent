"""Declared shapes for every error ``details`` block.

An error's ``details`` is a class instance, never a dict. That is the whole
point of this module: a field is named once, in a class declaration, so
``version`` at one raise site and ``revision`` at another is a typecheck
failure rather than two different keys on the buyer's wire. Before this,
``AdCPValidationError`` alone carried 30 distinct key sets across 34 sites,
with ``validation_errors``, ``creative_errors``, ``config_errors``,
``adapter_errors`` and ``violations`` all naming "a list of problems".

A detail class does NOT name an error code, deliberately. The EXCEPTION class
is the authority on which code it is; a detail shape is just a shape, and the
same shape legitimately serves several errors. ``{package_id, media_buy_id}``
fits both ``AdCPPackageNotFoundError`` and ``AdCPGamUpdateError``, and
``{creative_id}`` already appears under three different error classes. Putting
a code here would invert that authority and force a copy of the shape per
error.

The pairing is declared exactly once, in the exception's type parameter:
``class AdCPPackageNotFoundError(AdCPError[EntityRefDetails])``. mypy enforces
it at every raise site, and the advisory lane reads the code off the exception
via ``Error.from_exception()`` rather than off the details.

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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.core.config import get_pydantic_extra_mode
from src.core.errors.codes import ErrorCodeT

__all__ = [
    "CreativeRejectionDetails",
    "TimeWindowDetails",
    "RejectionReasonDetails",
    "PolicyViolationDetails",
    "InvalidStateDetails",
    "ConflictDetails",
    "BudgetDetails",
    "AccountSetupDetails",
    "AccountAmbiguousDetails",
    "AdapterFailureDetails",
    "CapabilityRefusalDetails",
    "EntityRefDetails",
    "ErrorDetails",
    "ErrorProblem",
    "ProblemsDetails",
    "ProductRefDetails",
    "UpstreamCallDetails",
    "ValueRejectionDetails",
    "VersionUnsupportedDetails",
]


class ErrorDetails(BaseModel):
    """Base for every error-details shape.

    Carries fields only. Which error a shape belongs to is declared by the
    exception's type parameter, not here.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

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

    supported_versions: list[str]
    supported_majors: list[int] | None = None
    build_version: str | None = None
    adcp_version: str | None = None
    adcp_major_version: int | None = None


# ---------------------------------------------------------------------------
# Shared shapes. A shape names no code (see the module docstring), so one shape
# serves every error whose details answer the same question. These three cover
# the 11 key-sets the AST survey found already duplicated across error classes:
# {account_id} under four, {product_id} and {media_buy_id} under three each,
# {agent_url, format_id} under three, and so on. Before this they were 11
# copies of the same idea, distinguishable only by which raise site you read.
# ---------------------------------------------------------------------------


class EntityRefDetails(ErrorDetails):
    """WHICH entity the error is about.

    One shape for the not-found family, the ownership checks, and every error
    whose details are simply "here is the identifier you asked about". Every
    field is optional because a site names the identifiers it actually knows —
    a package lookup that failed before resolving its media buy has only the
    package id.

    Shared deliberately across errors with different codes.
    ``AdCPPackageNotFoundError`` and ``AdCPGamUpdateError`` both answer "which
    package", and the code says what went wrong with it.
    """

    account_id: str | None = None
    media_buy_id: str | None = None
    package_id: str | None = None
    product_id: str | None = None
    creative_id: str | None = None
    format_id: str | None = None
    line_item_id: str | None = None
    context_id: str | None = None
    step_id: str | None = None
    principal_id: str | None = None
    tenant_id: str | None = None
    agent_url: str | None = None
    brand_domain: str | None = None
    operator: str | None = None
    idempotency_key: str | None = None
    package_index: int | None = None
    format_index: int | None = None


class UpstreamCallDetails(ErrorDetails):
    """What happened on a call OUT of this seller, to an adapter or agent.

    Distinct from ``EntityRefDetails`` because these fields describe the call,
    not the entity: a buyer reading ``status_code`` learns about the seller's
    upstream, and a buyer reading ``package_id`` learns about their own request.
    """

    agent_name: str | None = None
    url: str | None = None
    status: str | None = None
    status_code: int | None = None
    max_retries: int | None = None


class ProblemsDetails(ErrorDetails):
    """A collection of problems, each one structured.

    Replaces the five key names that all meant this — ``validation_errors``,
    ``creative_errors``, ``config_errors``, ``adapter_errors`` and
    ``violations`` — every one of which held ``list[str]`` built by discarding
    the structure it interpolated. See ``ErrorProblem``.
    """

    problems: list[ErrorProblem] | None = None


class ProductRefDetails(EntityRefDetails):
    """A product reference that may name several products at once.

    Extends ``EntityRefDetails`` rather than redeclaring its fields: a
    product-not-found either names the one product asked for, or the set that
    could not be resolved from a multi-package request.
    """

    missing_product_ids: list[str] | None = None


class AdapterFailureDetails(EntityRefDetails, UpstreamCallDetails, ProblemsDetails):
    """A failure on a call out to an adapter or agent.

    Composed rather than redeclared. An adapter failure genuinely needs all
    three axes: which entity the call was about (``EntityRefDetails``), what the
    upstream did (``UpstreamCallDetails``), and the per-item problems when the
    call partially succeeded (``ProblemsDetails``). Listing those fields again
    here would be the copy-paste the DRY invariant forbids, and the composition
    is why ``AdCPAdapterError`` needs no type parameter of its own -- its five
    taxonomy subclasses all draw from the same three axes.
    """


class ValueRejectionDetails(ErrorDetails):
    """A value the buyer supplied was refused, and optionally what is accepted.

    ``rejected_value`` and ``accepted_values`` are the pin's canonical
    rejection-set keys (v3.1.1 ``core/error.json``, the ``details`` description),
    named there explicitly "rather than seller-specific variants observed in the
    wild (``available``, ``allowed`` ...)".

    This replaces eight sites whose detail key merely REPEATED the field name —
    ``field='brand'`` beside ``details={'brand': raw}``, ``field='status'``
    beside ``details={'status': status}``. Eight key names for one concept, none
    of which a buyer could read without first reading ``field``.

    ``rejected_value`` admits a list because a list-valued field's offending
    value IS the list; splitting it into a second ``rejected_values`` field would
    be two channels for one fact.
    """

    rejected_value: str | list[str] | None = None
    accepted_values: list[str] | None = None
    received_type: str | None = None


class CapabilityRefusalDetails(EntityRefDetails, ValueRejectionDetails):
    """A capability the buyer asked for that this seller does not support.

    One shape for 28 sites that previously used 18 different key names, because
    they put the CAPABILITY NAME IN THE KEY: ``{"device_type_any_of": [...]}``,
    ``{"os_any_of": [...]}``, ``{"geo_system": ..., "supported_systems": [...]}``.
    A buyer had to know every key name in advance to find out which capability
    was refused. Naming it in ``capability`` makes one read work for all of them,
    and the requested/supported pair uses the pin's canonical keys.
    """

    capability: str | None = None


class BudgetDetails(EntityRefDetails):
    """A budget refusal, with the numbers that decided it.

    Deliberately NOT borrowing ``budget-too-low.json``'s ``minimum_budget`` /
    ``currency``: that shape governs ``BUDGET_TOO_LOW``, and importing its key
    names under ``BUDGET_EXCEEDED`` would claim a pinned shape for a code the pin
    does not associate with it.
    """

    requested_budget: str | None = None
    current_spend: str | None = None
    budget_limit: str | None = None


class RejectionReasonDetails(ErrorDetails):
    """A seller's own reason for declining, as configured by that seller.

    ``rejection_reason`` is OPERATOR data, not a buyer-facing sentence this repo
    authored: it comes from the seller's approval configuration, and the buyer
    genuinely needs it to know why the decline happened. It stays free text for
    that reason, and only that reason.
    """

    rejection_reason: str | None = None


class AccountSetupDetails(EntityRefDetails):
    """An account that needs work before it can be used.

    ``setup_url`` and ``setup_steps`` are ``account-setup-required.json``'s own
    property names, so this uses them rather than a local synonym.
    """

    setup_url: str | None = None
    setup_steps: list[str] | None = None


class AccountAmbiguousDetails(EntityRefDetails):
    """A reference that resolved to more than one account."""

    match_count: int | None = None


class InvalidStateDetails(EntityRefDetails):
    """The resource's current status, and what that status forbids."""

    current_status: str | None = None
    disallowed_actions: list[str] | None = None


class PolicyViolationDetails(ErrorDetails):
    """A policy refusal. Field names from ``policy-violation.json``.

    ``violated_rules`` is the pin's name for what this repo called
    ``restrictions`` — the same fact, so the pinned spelling wins.
    """

    policy_id: str | None = None
    policy_url: str | None = None
    violated_rules: list[str] | None = None


class ConflictDetails(EntityRefDetails):
    """A conflicting resource. ``resource_id`` is ``conflict.json``'s own name.

    ``expected_version`` / ``current_version`` are declared because the pin
    declares them, even though no site populates them yet: a buyer reading the
    pinned shape should find the keys where the pin says they are.
    """

    resource_id: str | None = None
    expected_version: str | None = None
    current_version: str | None = None
    status: str | None = None


class TimeWindowDetails(ErrorDetails):
    """A start/end pair that is invalid as a pair, not individually.

    Distinct from ``ValueRejectionDetails.rejected_value``: one offending value
    goes there, but a window is refused for the RELATIONSHIP between two
    instants, so both have to be readable.
    """

    start_time: str | None = None
    end_time: str | None = None


class CreativeRejectionDetails(EntityRefDetails, ValueRejectionDetails, ProblemsDetails):
    """A creative this seller will not accept.

    ``policy_id``, ``policy_url`` and ``reasons`` are ``creative-rejected.json``'s
    own properties, so they carry the pin's spelling. Sixteen sites previously
    used eleven key names, several of which were synonyms for one of those three:
    ``rejection_reasons`` and ``creative_errors`` are both ``reasons``, and
    ``supported_formats`` is the pin-canonical ``accepted_values`` this shape
    inherits.

    The fields below the FIXME are NOT in the pinned shape. They are conformant
    (``additionalProperties: true``) and they preserve what each site emits
    today, which is this migration's rule. Whether they belong in ``details`` at
    all is the open question: ``missing_field`` / ``invalid_field`` name a field,
    which is what the top-level ``field`` pointer and ``issues[]`` exist for, and
    ``creative_ids`` identifies subjects, which ``problems[].subject_id`` already
    carries per item.
    """

    policy_id: str | None = None
    policy_url: str | None = None
    reasons: list[str] | None = None

    # FIXME(#2099): not declared by creative-rejected.json. See the docstring.
    creative_ids: list[str] | None = None
    missing_field: str | None = None
    invalid_field: str | None = None
