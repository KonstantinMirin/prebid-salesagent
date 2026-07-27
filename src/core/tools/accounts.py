"""Account tool implementations (list + sync).

Handles account management per AdCP spec (UC-011):
- Agent-scoped results (BR-RULE-054)
- Auth-optional list with empty fallback (BR-RULE-055)
- Upsert by natural key (BR-RULE-056)
- Atomic XOR response (BR-RULE-057)
- Brand echo (BR-RULE-058)
- Approval workflow (BR-RULE-060)
- delete_missing (BR-RULE-061)
- dry_run (BR-RULE-062)

beads: salesagent-hl0, salesagent-619
"""

import base64
import logging
import time
import uuid
from datetime import UTC
from typing import Annotated, Any

from adcp.types import AccountReference as LibraryAccountReference
from adcp.types import ContextObject, PaginationRequest, PaginationResponse
from adcp.types.generated_poc.account.list_accounts_request import (
    Status as AccountStatus,
)
from adcp.types.generated_poc.account.sync_accounts_request import (
    Accounts as SyncAccountInput,  # SDK 5.7: Account → Accounts
)
from adcp.types.generated_poc.account.sync_accounts_request import (
    Accounts1 as SettingsUpdateAccountInput,  # the account-reference / settings-update arm
)
from adcp.types.generated_poc.core.account_ref import AccountReference1
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from src.core.audit_logger import get_audit_logger
from src.core.auth import require_identity, require_principal_id, require_tenant
from src.core.database.models import Account as DBAccount
from src.core.database.repositories.uow import AccountUoW
from src.core.exceptions import AdCPValidationError
from src.core.helpers import enum_value
from src.core.resolved_identity import ResolvedIdentity
from src.core.schemas.account import (
    Account,
    ListAccountsRequest,
    ListAccountsResponse,
    SyncAccountsRequest,
    SyncAccountsResponse,
    SyncResponseAccount,
)
from src.core.tool_context import ToolContext
from src.core.tools._mcp_boundary import build_tool_result
from src.core.transport_helpers import NOT_PROVIDED, IdentityOrNotProvided, resolve_identity_if_not_provided
from src.services.notification_proof_service import get_notification_proof_service

logger = logging.getLogger(__name__)


def _db_account_to_schema(db_account: DBAccount) -> Account:
    """Convert ORM Account to Pydantic schema Account."""
    return Account(
        account_id=db_account.account_id,
        name=db_account.name,
        status=db_account.status,
        advertiser=db_account.advertiser,
        billing_proxy=db_account.billing_proxy,
        brand=db_account.brand,
        operator=db_account.operator,
        billing=db_account.billing,
        rate_card=db_account.rate_card,
        payment_terms=db_account.payment_terms,
        credit_limit=db_account.credit_limit,
        setup=db_account.setup,
        account_scope=db_account.account_scope,
        governance_agents=db_account.governance_agents,
        sandbox=db_account.sandbox,
        # Same scrub as the sync echo: list_accounts must not reflect write-only
        # credentials either, and the read-back leg of the register scenario goes
        # through here.
        notification_configs=_scrub_notification_credentials(db_account.notification_configs),
        ext=db_account.ext,
    )


def _encode_cursor(offset: int) -> str:
    """Encode an offset as a base64 cursor string."""
    return base64.b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    """Decode a base64 cursor string to an offset. Returns 0 for invalid cursors."""
    try:
        return int(base64.b64decode(cursor).decode())
    except (ValueError, Exception):
        return 0


def _apply_pagination(
    accounts: list[Account],
    pagination: PaginationRequest | None,
) -> tuple[list[Account], PaginationResponse | None]:
    """Apply cursor-based pagination to an account list.

    Returns (paginated_accounts, pagination_response_or_None).
    """
    if pagination is None:
        return accounts, None

    max_results = pagination.max_results or 50
    offset = _decode_cursor(pagination.cursor) if pagination.cursor else 0

    paginated = accounts[offset : offset + max_results]
    has_more = (offset + max_results) < len(accounts)

    return paginated, PaginationResponse(
        has_more=has_more,
        cursor=_encode_cursor(offset + max_results) if has_more else None,
        total_count=len(accounts),
    )


def _matches_account_ref(db_account: Any, ref: Any) -> bool:
    """Whether *db_account* matches an AccountReference (account_id XOR natural key).

    AccountReference1 carries account_id; AccountReference2 carries the natural
    key (brand + operator, optionally sandbox) -- mirrors the RootModel
    discrimination in _process_settings_update_entry (salesagent-5g8e).
    """
    if isinstance(ref, AccountReference1):
        return bool(db_account.account_id == ref.account_id)
    brand_domain = ref.brand.domain if ref.brand else None
    if db_account.operator != ref.operator:
        return False
    # brand is Mapped[BrandReference | None] (JSONType(model=BrandReference),
    # models.py:828) -- hydrated as the typed model, not a plain dict.
    domain = db_account.brand.domain if db_account.brand else None
    if domain != brand_domain:
        return False
    if ref.sandbox is not None and db_account.sandbox != ref.sandbox:
        return False
    return True


def _apply_list_account_filters(db_accounts: list[Any], req: Any) -> list[Any]:
    """Apply every list_accounts predicate filter in one place (DRY --
    salesagent-tm97 disease scan; status/sandbox/account were 3 near-identical
    inline list-comprehension filters before this extraction).
    """
    status_filter = getattr(req, "status", None)
    if status_filter is not None:
        status_str = enum_value(status_filter)
        db_accounts = [a for a in db_accounts if a.status == status_str]

    sandbox_filter = getattr(req, "sandbox", None)
    if sandbox_filter is not None:
        db_accounts = [a for a in db_accounts if a.sandbox == sandbox_filter]

    account_filter = getattr(req, "account", None)
    if account_filter is not None:
        # account_filter is always AccountReference (a RootModel) when present.
        db_accounts = [a for a in db_accounts if _matches_account_ref(a, account_filter.root)]

    return db_accounts


def _list_accounts_impl(
    req: ListAccountsRequest | None = None,
    identity: ResolvedIdentity | None = None,
) -> ListAccountsResponse:
    """List accounts accessible to the authenticated agent.

    Per BR-RULE-055: requires authentication, raises AUTH_MISSING if missing.
    Per BR-RULE-054: returns only accounts accessible to the agent.

    Args:
        req: Optional request with status filter and pagination.
        identity: Resolved identity for authentication.

    Returns:
        ListAccountsResponse with scoped account list.
    """
    if req is None:
        req = ListAccountsRequest()

    # BR-RULE-055 INV-3: unauthenticated → auth error (consistent with sync_accounts)
    principal_id = require_principal_id(identity, context=req.context)
    tenant = require_tenant(identity, context=req.context)
    tenant_id = tenant["tenant_id"]

    with AccountUoW(tenant_id) as uow:
        assert uow.accounts is not None
        # BR-RULE-054: agent-scoped results
        db_accounts = uow.accounts.list_for_agent(principal_id)
        db_accounts = _apply_list_account_filters(db_accounts, req)

        # Sort for deterministic pagination
        db_accounts.sort(key=lambda a: a.account_id)

        # Convert ORM models to schema models while session is alive
        schema_accounts = [_db_account_to_schema(a) for a in db_accounts]

    # Apply pagination after conversion
    paginated, pagination_resp = _apply_pagination(schema_accounts, getattr(req, "pagination", None))

    return ListAccountsResponse(
        accounts=paginated,
        pagination=pagination_resp,
        context=req.context,
    )


# ---------------------------------------------------------------------------
# MCP wrapper
# ---------------------------------------------------------------------------


async def list_accounts(
    account: LibraryAccountReference | None = None,
    status: AccountStatus | None = None,
    pagination: PaginationRequest | None = None,
    sandbox: Annotated[bool | None, Field(description="When true, return only sandbox/test accounts")] = None,
    idempotency_key: Annotated[
        str | None, Field(description="Read-tool idempotency tolerance per v3.1.1 -- accepted, has no effect")
    ] = None,
    ext: Annotated[dict | None, Field(description="AdCP extension object -- accepted, has no effect")] = None,
    context: ContextObject | None = None,
    ctx: Context | ToolContext | None = None,
) -> Any:
    """List accounts accessible to the authenticated agent (MCP tool).

    MCP wrapper that delegates to the shared implementation.
    FastMCP automatically validates and coerces JSON inputs to Pydantic models.

    Args:
        account: Exact account filter (account_id, or natural key brand+operator[+sandbox]).
        status: Filter accounts by status (active, closed, etc.).
        pagination: Pagination parameters (max_results, cursor).
        sandbox: Filter by sandbox flag.
        idempotency_key: Read-tool idempotency tolerance (accepted, no effect on a read).
        ext: AdCP extension object (accepted, no effect).
        context: Application-level context per AdCP spec.
        ctx: FastMCP context for authentication.

    Returns:
        ToolResult with human-readable text and structured data.
    """
    req = ListAccountsRequest(
        account=account,
        status=status,
        pagination=pagination,
        sandbox=sandbox,
        idempotency_key=idempotency_key,
        ext=ext,
        context=context,
    )

    identity = (await ctx.get_state("identity")) if isinstance(ctx, Context) else None
    response = _list_accounts_impl(req, identity)

    return build_tool_result(str(response), response)


# ---------------------------------------------------------------------------
# A2A raw wrapper
# ---------------------------------------------------------------------------


def list_accounts_raw(
    req: ListAccountsRequest | None = None,
    ctx: Context | ToolContext | None = None,
    identity: IdentityOrNotProvided = NOT_PROVIDED,
) -> ListAccountsResponse:
    """List accounts accessible to the authenticated agent (raw function for A2A).

    Args:
        req: Optional request with filter parameters.
        ctx: FastMCP context.
        identity: Pre-resolved identity (if available).

    Returns:
        ListAccountsResponse with accessible accounts.
    """
    identity = resolve_identity_if_not_provided(identity, ctx, require_valid_token=False)
    return _list_accounts_impl(req, identity)


# ===========================================================================
# sync_accounts — upsert accounts by natural key (BR-RULE-056..062)
# ===========================================================================


def _generate_account_id() -> str:
    """Generate a unique account ID."""
    return f"acc_{uuid.uuid4().hex[:12]}"


def _generate_account_name(brand_domain: str, operator: str, brand_id: str | None = None) -> str:
    """Generate a human-readable account name from brand + operator."""
    brand_part = f"{brand_domain}:{brand_id}" if brand_id else brand_domain
    return f"{brand_part} c/o {operator}"


def _enum_to_str(val: Any) -> str | None:
    """Extract string value from an enum or return as-is. Returns None for None."""
    return enum_value(val)


def _serialize_typed_list(items: Any, model: type[BaseModel]) -> list[dict[str, Any]] | None:
    """Normalize a list of typed models (or dicts) to JSON-serializable dicts.

    Both dict and model inputs go through ``model_dump(mode="json")`` so that
    comparison is type-stable — without it ``AnyUrl != str`` and an unchanged
    field reads as changed on every sync.

    ``None`` and ``[]`` are preserved as distinct results: for
    ``notification_configs`` they mean "never configured" and "explicitly
    cleared", which the wire must tell apart.
    """
    if items is None:
        return None
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            # Validate through the model to normalize types (AnyUrl -> str, etc.)
            result.append(model.model_validate(item).model_dump(mode="json"))
        elif hasattr(item, "model_dump"):
            result.append(item.model_dump(mode="json"))
        else:
            result.append(dict(item))
    return result


def _serialize_governance_agents(agents: Any) -> list[dict[str, Any]] | None:
    """Convert GovernanceAgent models to JSON-serializable dicts for DB storage."""
    from adcp.types.generated_poc.core.account import GovernanceAgent  # TODO: no stable alias in adcp.types

    return _serialize_typed_list(agents, GovernanceAgent)


def _serialize_notification_configs(configs: Any) -> list[dict[str, Any]] | None:
    """Convert NotificationConfig models to JSON-serializable dicts for DB storage."""
    from adcp.types import NotificationConfig

    return _serialize_typed_list(configs, NotificationConfig)


def _scrub_notification_credentials(configs: Any) -> list[Any] | None:
    """Strip write-only ``authentication.credentials`` from an echoed subscriber set.

    ``credentials`` is ``minLength: 32`` and documented write-only: the seller
    stores it to authenticate its own outbound calls and MUST NOT reflect it.
    Called from ``_build_sync_result`` and ``_db_account_to_schema`` — the two
    places a persisted config becomes a response object — rather than at each
    call site, so a future echo path cannot forget it.

    Returns ``None`` for ``None`` and ``[]`` for ``[]``: "never configured" and
    "explicitly cleared" are different states to the buyer.
    """
    from adcp.types import NotificationConfig

    if configs is None:
        return None
    scrubbed: list[Any] = []
    for config in configs:
        data = config.model_dump(mode="json") if hasattr(config, "model_dump") else dict(config)
        auth = data.get("authentication")
        if isinstance(auth, dict) and "credentials" in auth:
            auth = {k: v for k, v in auth.items() if k != "credentials"}
            data["authentication"] = auth
        scrubbed.append(NotificationConfig.model_validate(data))
    return scrubbed


def _resolve_notification_configs(entry: Any, existing: Any) -> tuple[bool, list[dict[str, Any]] | None]:
    """Apply declarative-replace semantics for ``notification_configs``.

    Returns ``(changed, value)``:
      - field omitted (``None``) -> ``(False, existing)``: omission is NOT clearance
      - ``[]``                   -> ``(True, [])``: explicit clear, persisted as an
        empty array rather than NULL so the echo can carry it
      - non-empty                -> ``(True, <full array>)``: the submitted array
        REPLACES the persisted set wholesale; a re-sent ``subscriber_id`` replaces
        in place and paused entries survive only if re-included. Never merged.

    Note the ``is None`` test: ``[]`` is falsy, so a truthiness check here would
    silently turn "clear" into "leave unchanged".
    """
    submitted = getattr(entry, "notification_configs", None)
    if submitted is None:
        return False, existing
    return True, _serialize_notification_configs(submitted) or []


def _account_fields_changed(db_account: DBAccount, entry: Any) -> dict[str, Any]:
    """Compare incoming sync entry fields against existing DB account.

    Returns a dict of fields that changed (key → new value).
    Only compares mutable fields that can be updated via sync.
    """
    changes: dict[str, Any] = {}

    billing_val = _enum_to_str(entry.billing)
    if db_account.billing != billing_val:
        changes["billing"] = billing_val

    payment_terms_val = _enum_to_str(entry.payment_terms)
    if db_account.payment_terms != payment_terms_val:
        changes["payment_terms"] = payment_terms_val

    # Normalize: None and False are equivalent for sandbox (DB defaults to False)
    sandbox_val = entry.sandbox or False
    db_sandbox = db_account.sandbox or False
    if db_sandbox != sandbox_val:
        changes["sandbox"] = entry.sandbox

    # Compare governance_agents (JSON field)
    # Both sides must be serialized to dicts for comparison — db_account.governance_agents
    # is hydrated to list[GovernanceAgent] by JSONType, while incoming is already serialized.
    incoming_gov = _serialize_governance_agents(getattr(entry, "governance_agents", None))
    db_gov = _serialize_governance_agents(db_account.governance_agents)
    if db_gov != incoming_gov:
        changes["governance_agents"] = incoming_gov

    # notification_configs gets its OWN branch, not a fold into the governance_agents
    # comparison above: its semantics differ (omission PRESERVES rather than clears,
    # and [] is a meaningful value), so the generic "serialize both sides and compare"
    # rule would turn an omitted field into a clear.
    notif_changed, notif_value = _resolve_notification_configs(
        entry, _serialize_notification_configs(db_account.notification_configs)
    )
    if notif_changed and notif_value != _serialize_notification_configs(db_account.notification_configs):
        changes["notification_configs"] = notif_value

    return changes


def _build_sync_result(
    *,
    brand: Any,
    operator: str,
    action: str,
    status: str,
    account_id: str | None = None,
    name: str | None = None,
    billing: str | None = None,
    payment_terms: str | None = None,
    sandbox: bool | None = None,
    errors: list[Any] | None = None,
    setup: Any | None = None,
    notification_configs: Any | None = None,
) -> SyncResponseAccount:
    """Build an AdCP sync response Account object.

    The seller-assigned ``account_id`` MUST be echoed back for any non-failure
    action (created/updated/unchanged) so the buyer can reference the account
    in subsequent calls (BR-UC-011 POST-S5). Only ``failed`` results legitimately
    omit it because no account was provisioned.

    ``notification_configs`` is scrubbed of write-only credentials HERE rather
    than at the call sites: this builder exists so a shared shape can't drift
    across call sites, which makes it the one place a leak cannot be introduced
    by forgetting a call.
    """
    return SyncResponseAccount(
        brand=brand,
        operator=operator,
        action=action,
        status=status,
        account_id=account_id,
        name=name,
        billing=billing,
        payment_terms=payment_terms,
        sandbox=sandbox,
        errors=errors,
        setup=setup,
        notification_configs=_scrub_notification_credentials(notification_configs),
    )


def _build_failed_result(
    *,
    brand: Any,
    operator: str,
    billing: str | None,
    sandbox: bool | None,
    errors: list[Any],
) -> SyncResponseAccount:
    """Build a failed/rejected sync result -- the single source for every
    per-entry gate rejection (domain validity, billing policy, sandbox
    capability, settings-update-not-found), so a shared shape can't drift
    across call sites (salesagent-5g8e disease scan).
    """
    return _build_sync_result(
        brand=brand,
        operator=operator,
        action="failed",
        status="rejected",
        billing=billing,
        sandbox=sandbox,
        errors=errors,
    )


def _build_setup_for_approval(mode: str, tenant_id: str) -> Any:
    """Build a Setup object based on the approval mode.

    Returns Setup for pending_approval modes, None for auto-approve.
    """
    from datetime import datetime, timedelta

    from adcp.types import Setup  # SDK 5.7: moved from sync_accounts_response to adcp.types

    if mode == "credit_review":
        return Setup(
            message="Account requires credit review before activation. Please complete the credit application.",
            url=f"https://seller.example.com/accounts/review?tenant={tenant_id}",
            expires_at=datetime.now(tz=UTC) + timedelta(days=7),
        )
    if mode == "legal_review":
        return Setup(
            message="Account requires legal review before activation. Our team will review your application.",
        )
    return None


def _check_domain_validity(brand_domain: str) -> list[Any] | None:
    """Check if the brand domain is valid for account provisioning.

    Returns a list of Error objects if invalid, None if valid.
    Reserved TLDs (.test, .invalid, .example, .localhost) are rejected.
    """
    from adcp.types import Error

    from src.core.security.url_validator import RESERVED_TLDS

    for tld in RESERVED_TLDS:
        if brand_domain.endswith(tld):
            return [
                Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                    code="VALIDATION_ERROR",
                    message=f"Domain '{brand_domain}' uses reserved TLD '{tld}' "
                    f"and cannot be used for account provisioning.",
                    suggestion="Use a real domain name for production accounts.",
                    field="brand.domain",
                )
            ]
    return None


def _check_billing_policy(
    billing_val: str | None,
    identity: ResolvedIdentity,
) -> list[Any] | None:
    """Check if the billing model is supported by the seller.

    Returns a list of Error objects if rejected, None if accepted.
    Per BR-RULE-059: unsupported billing → BILLING_NOT_SUPPORTED.
    """
    from adcp.types import Error

    from src.core.billing_policy import resolve_supported_billing

    # BR-RULE-059 governs UNSUPPORTED billing, not OMITTED billing — an
    # omitted (None) billing is never rejected, configured tenant or not.
    if billing_val is None:
        return None

    # Read billing policy from tenant configuration (not identity).
    # Both dict and TenantContext expose .get() identically, so no branching needed.
    tenant = identity.tenant if identity else None
    supported = resolve_supported_billing(tenant)

    if billing_val not in supported:
        # billing-not-supported.json: supported_billing minItems 1, "Sellers MAY
        # omit this field" -- an empty resolved policy must omit the key entirely,
        # never emit a schema-invalid empty array (salesagent-hh1f review MEDIUM #1).
        details: dict[str, Any] = {"scope": "capability"}
        supported_suffix = ""
        if supported:
            details["supported_billing"] = supported
            supported_suffix = f" Supported models: {', '.join(supported)}."
        return [
            Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                code="BILLING_NOT_SUPPORTED",
                message=f"Billing model '{billing_val}' is not supported by this seller.{supported_suffix}",
                suggestion=f"Use one of the supported billing models: {', '.join(supported)}."
                if supported
                else "Contact the seller to enable a supported billing model.",
                recovery="correctable",
                details=details,
            )
        ]
    return None


def _extract_natural_key(entry: Any) -> tuple[str, str | None, str, bool | None]:
    """Extract natural key components from a PROVISIONING-mode sync request entry.

    Returns (brand_domain, brand_id, operator, sandbox).

    Callers dispatch settings-update entries (``entry.account`` set) to
    ``_process_settings_update_entry`` BEFORE reaching this function — an
    entry that lands here with no ``brand`` carries neither the provisioning
    trio nor an account reference, a genuinely malformed request the pinned
    3.1 spec's ``required: ["brand", "operator", "billing"]`` (provisioning
    arm) rejects as a buyer-correctable 400 (salesagent-5g8e; previously this
    branch also caught settings-update entries before that mode was
    implemented — it no longer does).

    Raises:
        AdCPValidationError: if the entry omits ``brand``.
    """
    brand = entry.brand
    if brand is None:
        raise AdCPValidationError(
            "Each provisioning account entry must include 'brand', 'operator', and 'billing' "
            "(or 'account' for a settings-update entry).",
            recovery="correctable",
        )
    brand_domain = brand.domain
    brand_id = None
    if hasattr(brand, "brand_id") and brand.brand_id is not None:
        brand_id = str(brand.brand_id)
    operator = entry.operator
    sandbox = entry.sandbox
    return brand_domain, brand_id, operator, sandbox


def _check_sandbox_capability(entry_sandbox: bool | None, tenant: Any, index: int) -> list[Any] | None:
    """Reject sandbox provisioning when the seller has not declared account.sandbox support.

    Mirrors the ``_check_domain_validity``/``_check_billing_policy`` per-entry
    gate shape. BR-RULE-209 INV-6: only a seller with ``account.sandbox: true``
    (Tenant.account_sandbox) supports sandbox provisioning.
    """
    from adcp.types import Error

    if not entry_sandbox:
        return None
    if tenant and tenant.get("account_sandbox", True):
        return None
    return [
        Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
            code="UNSUPPORTED_FEATURE",
            message="Sandbox account provisioning was requested, but this seller does not "
            "declare account.sandbox support.",
            field=f"accounts[{index}].sandbox",
            suggestion="Check get_adcp_capabilities and remove the unsupported sandbox field, "
            "or provision a production account instead.",
            recovery="correctable",
        )
    ]


# Media-buy-anchored notification event types. These describe the lifecycle of a
# media buy's delivery reporting, not an account, so they do not belong on the
# account surface. There is deliberately no account-lifecycle event type either
# (no account.status_changed) -- poll list_accounts or use push_notification_config.
_MEDIA_BUY_ANCHORED_EVENT_TYPES = frozenset({"scheduled", "final", "delayed", "adjusted", "impairment"})


def _validate_notification_configs(configs: Any) -> list[Any] | None:
    """Validate a submitted notification_configs array; None when it is acceptable.

    Same per-entry gate shape as ``_check_domain_validity`` / ``_check_billing_policy``
    / ``_check_sandbox_capability``, and called from BOTH entry handlers so the two
    arms cannot drift.

    Check ORDER is load-bearing: the first failure decides the reported
    ``error.field``, and the scenarios pin exact pointers. Duplicates are detected
    before event scope so a duplicated entry reports its own
    ``[j].subscriber_id`` rather than some unrelated later field.

    These are per-account failures INSIDE a transport-level success -- the caller
    turns them into ``_build_failed_result``, never a transport error.
    """
    from adcp.types import Error

    from src.core.security.url_validator import check_url_syntax

    if not configs:
        return None

    seen_subscribers: set[str] = set()
    for index, config in enumerate(configs):
        subscriber_id = getattr(config, "subscriber_id", None)
        if subscriber_id in seen_subscribers:
            return [
                Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                    code="INVALID_REQUEST",
                    message=f"Duplicate subscriber_id '{subscriber_id}' in the submitted "
                    "notification_configs array; each subscriber_id may appear at most once.",
                    field=f"notification_configs[{index}].subscriber_id",
                    suggestion="Send one entry per subscriber_id -- the array declares the full "
                    "desired set, so a repeated id is ambiguous rather than an update.",
                    recovery="correctable",
                )
            ]
        if subscriber_id is not None:
            seen_subscribers.add(subscriber_id)

        for event_index, event_type in enumerate(getattr(config, "event_types", None) or []):
            if enum_value(event_type) in _MEDIA_BUY_ANCHORED_EVENT_TYPES:
                return [
                    Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                        code="INVALID_REQUEST",
                        message=f"Event type '{enum_value(event_type)}' is media-buy-anchored and "
                        "cannot be subscribed to on the account surface.",
                        field=f"notification_configs[{index}].event_types[{event_index}]",
                        suggestion="Subscribe to media-buy delivery events on the media buy itself; "
                        "account-level subscriptions carry creative and account-scoped events only.",
                        recovery="correctable",
                    )
                ]

        url = getattr(config, "url", None)
        # Syntax only -- NOT the DNS-resolving check_url_ssrf. A buyer may register
        # a webhook before standing the endpoint up, so requiring resolution at
        # write time would reject legitimate registrations. Reachability is the
        # activation proof's job (F4c), at fire time.
        url_ok, url_error = check_url_syntax(str(url), require_https=True)
        if not url_ok:
            return [
                Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                    code="INVALID_REQUEST",
                    message=f"notification_configs url is not acceptable: {url_error}",
                    field=f"notification_configs[{index}].url",
                    suggestion="Provide an absolute https:// URL on a publicly routable host.",
                    recovery="correctable",
                )
            ]
    return None


def _process_settings_update_entry(entry: Any, repo: Any, proof_errors: list[Any] | None = None) -> SyncResponseAccount:
    """Handle a settings-update entry (keyed by AccountReference) -- update an
    EXISTING account's settable fields, NEVER provision (F1b/F1c).

    ``entry.account`` is ``RootModel[AccountReference1 | AccountReference2]``:
    ``AccountReference1`` carries ``account_id`` (seller-assigned handle);
    ``AccountReference2`` carries the natural key (``brand``/``operator``/
    ``sandbox``). An unmatched reference is rejected with
    UNSUPPORTED_PROVISIONING -- a settings-update entry MUST NOT provision a
    new account under any circumstance.
    """
    from adcp.types import Error

    ref = entry.account.root
    if isinstance(ref, AccountReference1):
        existing = repo.get_by_id(ref.account_id)
    else:
        brand_domain = ref.brand.domain if ref.brand else None
        brand_id = None
        if ref.brand is not None and hasattr(ref.brand, "brand_id") and ref.brand.brand_id is not None:
            brand_id = str(ref.brand.brand_id)
        existing = repo.get_by_natural_key(
            operator=ref.operator,
            brand_domain=brand_domain,
            brand_id=brand_id,
            sandbox=ref.sandbox,
        )

    if existing is None:
        # brand/operator are REQUIRED on SyncResponseAccount. A natural-key reference
        # (AccountReference2) still carries brand/operator to echo even when unmatched;
        # an account_id reference (AccountReference1) carries none -- "unknown" is the
        # established placeholder convention in this file for exactly that situation
        # (cf. the publisher-domain placeholder above), not a fabricated real value.
        if isinstance(ref, AccountReference1):
            fail_brand: Any = {"domain": "unknown"}
            fail_operator = "unknown"
        else:
            fail_brand = ref.brand if ref.brand else {"domain": "unknown"}
            fail_operator = ref.operator or "unknown"
        return _build_failed_result(
            brand=fail_brand,
            operator=fail_operator,
            billing=None,
            sandbox=None,
            errors=[
                Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
                    code="UNSUPPORTED_PROVISIONING",
                    message="No existing account matches the provided account reference; "
                    "a settings-update entry never provisions a new account.",
                    suggestion="Provide 'brand', 'operator', and 'billing' to provision a new account instead.",
                    recovery="correctable",
                )
            ],
        )

    # Same shared validator as the provisioning arm, and BEFORE any write so a
    # rejected entry leaves the persisted array byte-identical.
    notif_errors = _validate_notification_configs(getattr(entry, "notification_configs", None))
    if notif_errors is None:
        # Same pre-computed verdicts as the provisioning arm: the proof ran before
        # any transaction opened, and a failure writes nothing for this entry.
        notif_errors = proof_errors
    if notif_errors is not None:
        return _build_failed_result(
            brand=existing.brand,
            operator=existing.operator or "",
            billing=existing.billing,
            sandbox=existing.sandbox,
            errors=notif_errors,
        )

    payment_terms_val = _enum_to_str(entry.payment_terms)
    changes: dict[str, Any] = {}
    if payment_terms_val is not None and payment_terms_val != existing.payment_terms:
        changes["payment_terms"] = payment_terms_val

    # notification_configs is "permitted in both provisioning and settings-update
    # modes" (sync-accounts-request.json), so the same shared resolver runs here --
    # not a second copy of the semantics.
    persisted_notif = _serialize_notification_configs(existing.notification_configs)
    notif_changed, notif_value = _resolve_notification_configs(entry, persisted_notif)
    if notif_changed and notif_value != persisted_notif:
        changes["notification_configs"] = notif_value

    action = "unchanged"
    if changes:
        repo.update_fields(existing.account_id, **changes)
        action = "updated"

    return _build_sync_result(
        brand=existing.brand,
        operator=existing.operator,
        action=action,
        status=existing.status,
        account_id=existing.account_id,
        name=existing.name,
        billing=existing.billing,
        payment_terms=existing.payment_terms,
        sandbox=existing.sandbox,
        # Post-write state: the applied array when this entry changed it, the
        # persisted one otherwise.
        notification_configs=changes.get("notification_configs", existing.notification_configs),
    )


#: Ceiling on how long ALL activation challenges in one request may take. The
#: per-challenge timeout bounds a single endpoint; without a request-level bound a
#: buyer could submit 16 configs x N accounts and hold a worker for minutes.
_PROOF_BUDGET_SECONDS = 6.0


def _proof_tuple(config: object) -> tuple:
    """The identity of a proof, per the spec's proof-reuse allowance.

    A re-sent config whose (subscriber_id, normalized url, auth binding, normalized
    event_types) matches an already-proven persisted entry MAY skip re-proof.
    """
    auth = getattr(config, "authentication", None)
    auth_scheme = getattr(auth, "scheme", None) if auth is not None else None
    return (
        getattr(config, "subscriber_id", None),
        str(getattr(config, "url", "") or "").rstrip("/"),
        enum_value(auth_scheme) if auth_scheme is not None else None,
        tuple(sorted(enum_value(e) for e in (getattr(config, "event_types", None) or []))),
    )


def _collect_activating_entries(entries: list[Any]) -> list[tuple[int, Any, Any]]:
    """(entry index, entry, config) for every config declaring ``active: true``."""
    activating: list[tuple[int, Any, Any]] = []
    for index, entry in enumerate(entries):
        for config in getattr(entry, "notification_configs", None) or []:
            if getattr(config, "active", False):
                activating.append((index, entry, config))
    return activating


def _proof_error(entry: Any, config: Any, message: str, suggestion: str) -> Any:
    """The per-account error a failed/skipped activation produces.

    One builder for both the dry_run and challenge-failure paths -- they carry the
    same code, recovery and field pointer, and only the explanation differs.
    """
    from adcp.types import Error

    return Error(  # structural-guard: advisory per-account result in SyncAccountsResponse.errors[]
        code="VALIDATION_ERROR",
        message=message,
        field=f"notification_configs[{_config_index(entry, config)}].url",
        suggestion=suggestion,
        recovery="correctable",
    )


def _already_proven_tuples(activating: list[tuple[int, Any, Any]], tenant_id: str) -> dict[int, set[tuple]]:
    """Proof tuples already persisted as active, per entry index.

    Its own SHORT read-only transaction, closed before any socket is opened -- the
    whole point of hoisting the proof out of the write transaction.
    """
    already_proven: dict[int, set[tuple]] = {}
    with AccountUoW(tenant_id) as uow:
        assert uow.accounts is not None
        for index, entry, _ in activating:
            existing = _lookup_existing_for_entry(entry, uow.accounts)
            if existing is None:
                continue
            already_proven.setdefault(index, set()).update(
                _proof_tuple(c) for c in (existing.notification_configs or []) if getattr(c, "active", False)
            )
    return already_proven


async def _resolve_activation_proofs(entries: list[Any], tenant_id: str, *, dry_run: bool) -> dict[int, list[Any]]:
    """Run proof-of-control for every entry activating a subscriber. Index -> errors.

    Runs BEFORE the write transaction opens: an outbound call inside an open
    Postgres transaction would hold it for the whole network round trip, which the
    owner's carve-out for in-request proof deliberately does not cover.

    Skipped entirely on ``dry_run``: a preview must not fire a request at a buyer's
    endpoint. Such an entry is reported as failed rather than previewed as active,
    because a preview must not claim an outcome it did not verify.
    """
    activating = _collect_activating_entries(entries)
    if not activating:
        return {}

    if dry_run:
        return {
            index: [
                _proof_error(
                    entry,
                    config,
                    "Activating a notification subscriber requires a proof-of-control challenge, "
                    "which dry_run does not perform; this preview cannot confirm the subscriber "
                    "would be activated.",
                    "Re-send without dry_run to perform the challenge.",
                )
            ]
            for index, entry, config in activating
        }

    already_proven = _already_proven_tuples(activating, tenant_id)
    prover = get_notification_proof_service()
    failures: dict[int, list[Any]] = {}
    budget = _PROOF_BUDGET_SECONDS

    for index, entry, config in activating:
        # Identical tuple already proven and persisted as active -- the spec permits
        # skipping re-proof, so no challenge is sent at all.
        if _proof_tuple(config) in already_proven.get(index, set()):
            continue
        proven, budget = await _prove_within_budget(prover, entry, config, budget)
        if not proven:
            failures.setdefault(index, []).append(
                _proof_error(
                    entry,
                    config,
                    "Proof-of-control challenge failed for the notification endpoint; the "
                    "subscriber was not activated and the account's previous notification_configs "
                    "are unchanged.",
                    "Ensure the endpoint answers the challenge POST with 2xx, then re-send.",
                )
            )
    return failures


async def _prove_within_budget(prover: Any, entry: Any, config: Any, budget: float) -> tuple[bool, float]:
    """Run one challenge if the request-level budget allows. Returns (proven, budget left).

    An exhausted budget is "not proven" rather than an unbounded wait: the caller is
    holding an HTTP request open.
    """
    if budget <= 0:
        return False, budget
    started = time.monotonic()
    proven = await prover.prove(_entry_account_hint(entry), config)
    return proven, budget - (time.monotonic() - started)


def _config_index(entry: Any, config: Any) -> int:
    """Position of *config* in *entry*'s submitted array (for error.field)."""
    for index, candidate in enumerate(getattr(entry, "notification_configs", None) or []):
        if candidate is config:
            return index
    return 0


def _entry_account_hint(entry: Any) -> str:
    """A human-meaningful account identifier for proof logging."""
    ref = getattr(entry, "account", None)
    if ref is not None and isinstance(getattr(ref, "root", None), AccountReference1):
        return str(ref.root.account_id)
    brand = getattr(entry, "brand", None)
    return str(getattr(brand, "domain", None) or "unknown")


def _lookup_existing_for_entry(entry: Any, repo: Any) -> Any:
    """Resolve the persisted account an entry targets, in either entry mode."""
    ref = getattr(entry, "account", None)
    if ref is not None:
        inner = ref.root
        if isinstance(inner, AccountReference1):
            return repo.get_by_id(inner.account_id)
        brand_domain = inner.brand.domain if inner.brand else None
        brand_id = None
        if inner.brand is not None and getattr(inner.brand, "brand_id", None) is not None:
            brand_id = str(inner.brand.brand_id)
        return repo.get_by_natural_key(
            operator=inner.operator, brand_domain=brand_domain, brand_id=brand_id, sandbox=inner.sandbox
        )
    brand = getattr(entry, "brand", None)
    if brand is None:
        return None
    brand_id = str(brand.brand_id) if getattr(brand, "brand_id", None) is not None else None
    return repo.get_by_natural_key(
        operator=entry.operator, brand_domain=brand.domain, brand_id=brand_id, sandbox=entry.sandbox
    )


async def _sync_accounts_impl(
    req: SyncAccountsRequest | None = None,
    identity: ResolvedIdentity | None = None,
) -> SyncAccountsResponse:
    """Sync accounts by natural key — upsert, delete_missing, dry_run.

    Per AdCP spec (BR-RULE-055..062):
    - Auth required (BR-RULE-055)
    - Upsert by natural key: brand.domain + brand.brand_id + operator + sandbox (BR-RULE-056)
    - Atomic XOR: success accounts[] or error errors[], never both (BR-RULE-057)
    - Brand echoed from request (BR-RULE-058)
    - New accounts get status=active (BR-RULE-060, auto-approve for now)
    - delete_missing closes absent accounts scoped to agent (BR-RULE-061)
    - dry_run previews without persisting (BR-RULE-062)

    Args:
        req: Sync request with accounts list and options.
        identity: Resolved identity (must be authenticated).

    Returns:
        SyncAccountsResponse with per-account action results.
    """
    if req is None:
        req = SyncAccountsRequest(accounts=[], idempotency_key=str(uuid.uuid4()))

    # BR-RULE-055: sync requires auth (consistent with list_accounts). require_principal_id
    # first so the canonical auth message surfaces for a missing/anonymous token; require_identity
    # then narrows the type for _check_billing_policy below.
    principal_id = require_principal_id(identity, context=req.context)
    identity = require_identity(identity, context=req.context)
    tenant = require_tenant(identity, context=req.context)
    tenant_id = tenant["tenant_id"]

    # Validate non-empty accounts array
    if not req.accounts:
        raise AdCPValidationError("accounts array must not be empty — at least one account is required.")
    dry_run = bool(req.dry_run)
    delete_missing = bool(req.delete_missing)

    results: list[SyncResponseAccount] = []
    # Track natural keys in the payload for delete_missing
    seen_account_ids: set[str] = set()

    # Activation proof runs BEFORE the write transaction opens (see
    # _resolve_activation_proofs). Holding a Postgres transaction across an
    # outbound HTTP call is what the owner's carve-out explicitly does not cover.
    proof_failures = await _resolve_activation_proofs(req.accounts, tenant_id, dry_run=dry_run)

    with AccountUoW(tenant_id) as uow:
        assert uow.accounts is not None
        repo = uow.accounts

        for index, entry in enumerate(req.accounts):
            # Mode-exclusivity guard (F1a): an entry carrying BOTH an account
            # reference and any provisioning-trio field violates the request
            # schema's item oneOf -- a structural, operation-level rejection,
            # not a per-account business-rule failure. Must run before any
            # dispatch; the SDK union has no real oneOf enforcement and would
            # otherwise silently parse this as the provisioning arm.
            if entry.account is not None and (
                entry.brand is not None or entry.operator is not None or entry.billing is not None
            ):
                raise AdCPValidationError(
                    f"accounts[{index}] carries both an account reference (settings-update) and "
                    "provisioning fields (brand/operator/billing) -- these are mutually exclusive.",
                    field=f"accounts[{index}]",
                    recovery="correctable",
                )

            if entry.account is not None:
                results.append(_process_settings_update_entry(entry, repo, proof_failures.get(index)))
                continue

            brand_domain, brand_id, operator, sandbox = _extract_natural_key(entry)
            billing_val = _enum_to_str(entry.billing)

            # Domain validation: reject reserved TLDs
            domain_errors = _check_domain_validity(brand_domain)
            if domain_errors is not None:
                results.append(
                    _build_failed_result(
                        brand=entry.brand,
                        operator=operator,
                        billing=billing_val,
                        sandbox=sandbox,
                        errors=domain_errors,
                    )
                )
                continue

            # BR-RULE-059: check billing policy before processing
            billing_errors = _check_billing_policy(billing_val, identity)
            if billing_errors is not None:
                results.append(
                    _build_failed_result(
                        brand=entry.brand,
                        operator=operator,
                        billing=billing_val,
                        sandbox=sandbox,
                        errors=billing_errors,
                    )
                )
                continue

            # BR-RULE-209 INV-6: sandbox provisioning requires a declared capability
            sandbox_errors = _check_sandbox_capability(sandbox, tenant, index)
            if sandbox_errors is not None:
                results.append(
                    _build_failed_result(
                        brand=entry.brand,
                        operator=operator,
                        billing=billing_val,
                        sandbox=sandbox,
                        errors=sandbox_errors,
                    )
                )
                continue

            # notification_configs validation runs BEFORE any write, so a rejected
            # entry leaves the account's prior array byte-identical. Same shared
            # validator as the settings-update arm.
            notif_errors = _validate_notification_configs(getattr(entry, "notification_configs", None))
            if notif_errors is None:
                # Proof verdicts were computed before this transaction opened; a
                # failure here means NOTHING is written for the entry, so the
                # account's prior array stays byte-identical.
                notif_errors = proof_failures.get(index)
            if notif_errors is not None:
                results.append(
                    _build_failed_result(
                        brand=entry.brand,
                        operator=operator,
                        billing=billing_val,
                        sandbox=sandbox,
                        errors=notif_errors,
                    )
                )
                continue

            # Look up existing account by natural key
            existing = repo.get_by_natural_key(
                operator=operator,
                brand_domain=brand_domain,
                brand_id=brand_id,
                sandbox=sandbox,
            )

            if existing is not None:
                seen_account_ids.add(existing.account_id)

                if dry_run:
                    # Check if fields would change
                    changes = _account_fields_changed(existing, entry)
                    action = "updated" if changes else "unchanged"
                    results.append(
                        _build_sync_result(
                            brand=entry.brand,
                            operator=operator,
                            action=action,
                            status=existing.status,
                            account_id=existing.account_id,
                            name=existing.name,
                            billing=existing.billing,
                            sandbox=existing.sandbox,
                            # Preview the array the write WOULD apply, not the
                            # persisted one -- a dry_run that echoed the old set
                            # would misreport what the buyer is about to change.
                            notification_configs=changes.get("notification_configs", existing.notification_configs),
                        )
                    )
                    continue

                # Check for field changes and update if needed
                changes = _account_fields_changed(existing, entry)
                if changes:
                    repo.update_fields(existing.account_id, **changes)
                    action = "updated"
                else:
                    action = "unchanged"

                results.append(
                    _build_sync_result(
                        brand=entry.brand,
                        operator=operator,
                        action=action,
                        status=existing.status,
                        account_id=existing.account_id,
                        name=existing.name,
                        billing=existing.billing,
                        sandbox=existing.sandbox,
                        # Post-write state: the applied array, which is the
                        # changed value when this sync touched it and the
                        # persisted one when it did not (omission preserves).
                        notification_configs=changes.get("notification_configs", existing.notification_configs),
                    )
                )
            else:
                # Create new account
                billing_val = _enum_to_str(entry.billing)
                payment_terms_val = _enum_to_str(entry.payment_terms)
                governance_agents_val = _serialize_governance_agents(getattr(entry, "governance_agents", None))
                # New account: there is no persisted set, so an omitted field
                # stays None ("never configured") rather than becoming [].
                _, notification_configs_val = _resolve_notification_configs(entry, None)

                account_id = _generate_account_id()
                account_name = _generate_account_name(brand_domain, operator, brand_id)

                # BR-RULE-060: determine approval status from tenant config.
                # account_approval_mode is a distinct field from creative approval_mode
                # (BR-RULE-037) — do NOT fall back to approval_mode.
                # Resolved BEFORE the dry_run branch so previews reflect what a real
                # create would return (BR-RULE-062).
                approval_mode = tenant.get("account_approval_mode")
                setup = _build_setup_for_approval(approval_mode or "auto", tenant_id)
                initial_status = "pending_approval" if setup else "active"

                if dry_run:
                    # account_id was generated above (BR-RULE-062 — preview reflects
                    # what a real create would return). It is a preview value, not a
                    # commitment to that specific id.
                    results.append(
                        _build_sync_result(
                            brand=entry.brand,
                            operator=operator,
                            action="created",
                            status=initial_status,
                            account_id=account_id,
                            name=account_name,
                            billing=billing_val,
                            sandbox=sandbox,
                            setup=setup,
                            notification_configs=notification_configs_val,
                        )
                    )
                    continue

                new_account = DBAccount(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    name=account_name,
                    status=initial_status,
                    brand={"domain": brand_domain, **({"brand_id": brand_id} if brand_id else {})},
                    operator=operator,
                    billing=billing_val,
                    payment_terms=payment_terms_val,
                    sandbox=sandbox,
                    governance_agents=governance_agents_val,
                    notification_configs=notification_configs_val,
                    principal_id=principal_id,
                )
                repo.create(new_account)
                seen_account_ids.add(account_id)

                # Grant agent access to the new account
                repo.grant_access(principal_id, account_id)

                results.append(
                    _build_sync_result(
                        brand=entry.brand,
                        operator=operator,
                        action="created",
                        status=initial_status,
                        account_id=account_id,
                        name=account_name,
                        billing=billing_val,
                        sandbox=sandbox,
                        setup=setup,
                        notification_configs=notification_configs_val,
                    )
                )

        # BR-RULE-061: delete_missing — close accounts not in payload
        if delete_missing and not dry_run:
            agent_accounts = repo.list_by_principal(principal_id)
            for db_acct in agent_accounts:
                if db_acct.account_id not in seen_account_ids:
                    repo.update_status(db_acct.account_id, "closed")
                    results.append(
                        _build_sync_result(
                            brand=db_acct.brand,
                            operator=db_acct.operator or "",
                            action="updated",
                            status="closed",
                            account_id=db_acct.account_id,
                            name=db_acct.name,
                            billing=db_acct.billing,
                            sandbox=db_acct.sandbox,
                        )
                    )

    # Audit log
    audit_logger = get_audit_logger("sync_accounts", tenant_id)
    action_counts: dict[str, int] = {}
    for r in results:
        act = _enum_to_str(r.action) or "unknown"
        action_counts[act] = action_counts.get(act, 0) + 1
    audit_logger.log_info(f"sync_accounts completed: {action_counts} (dry_run={dry_run}, principal={principal_id})")

    return SyncAccountsResponse(
        accounts=results,
        dry_run=dry_run if dry_run else None,
        context=req.context,
    )


# ---------------------------------------------------------------------------
# sync_accounts MCP wrapper
# ---------------------------------------------------------------------------


async def sync_accounts(
    accounts: list[SyncAccountInput | SettingsUpdateAccountInput] | None = None,
    delete_missing: Annotated[
        bool | None, Field(description="Deactivate accounts not present in the sync list")
    ] = None,
    dry_run: Annotated[bool | None, Field(description="Preview sync results without making changes")] = None,
    context: ContextObject | None = None,
    ctx: Context | ToolContext | None = None,
) -> Any:
    """Sync accounts by natural key (MCP tool).

    MCP wrapper that accepts individual parameters per AdCP spec and
    constructs a SyncAccountsRequest for the shared implementation.

    Args:
        accounts: List of accounts to upsert.
        delete_missing: Deactivate accounts not in the list.
        dry_run: Preview changes without persisting.
        context: Application-level context per AdCP spec.
        ctx: FastMCP context for authentication.

    Returns:
        ToolResult with human-readable text and structured data.
    """
    req = SyncAccountsRequest(
        accounts=accounts or [],
        delete_missing=delete_missing,
        dry_run=dry_run,
        context=context,
        idempotency_key=str(uuid.uuid4()),
    )
    identity = (await ctx.get_state("identity")) if isinstance(ctx, Context) else None
    response = await _sync_accounts_impl(req, identity)

    return build_tool_result(str(response), response)


# ---------------------------------------------------------------------------
# sync_accounts A2A raw wrapper
# ---------------------------------------------------------------------------


async def sync_accounts_raw(
    req: SyncAccountsRequest | None = None,
    ctx: Context | ToolContext | None = None,
    identity: IdentityOrNotProvided = NOT_PROVIDED,
) -> SyncAccountsResponse:
    """Sync accounts by natural key (raw function for A2A).

    Args:
        req: Sync request with accounts to upsert.
        ctx: FastMCP context.
        identity: Pre-resolved identity (if available).

    Returns:
        SyncAccountsResponse with per-account action results.
    """
    identity = resolve_identity_if_not_provided(identity, ctx, require_valid_token=True)
    return await _sync_accounts_impl(req, identity)
