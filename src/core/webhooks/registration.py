"""A webhook registration that is valid *by having been constructed*.

Core Invariant (Epic D, lane C1): there is no callable path that runs the URL
half of a push-notification registration without also running the credential
half, and :class:`~src.core.security.webhook_egress.HmacSecretMissing` exists
only between the resolver and the refusal -- never inside a value that outlives
the call.

Before this module, "this registration is valid" was a *remembered call* over
primitives: ``reject_unsafe_webhook_registration_url`` (URL half) and
``reject_invalid_webhook_registration`` (both halves) sat side by side, so of
the five registration surfaces two remembered both halves and three remembered
only the URL half. A buyer registering ``HMAC-SHA256`` with no credentials was
accepted on those three, and then never delivered to -- the fail-closed sender
branches refuse to send unsigned what was registered signed. Accept-then-never-
deliver was reachable because the wrong thing required importing nothing and
the right thing required a type that did not exist.

The type is that missing thing. :attr:`ValidatedWebhookRegistration.auth` is
annotated ``DeliverableWebhookAuth`` -- the ``WebhookAuth`` union MINUS
``HmacSecretMissing`` -- so mypy refuses a laundered value, and
``__post_init__`` refuses one at runtime. The invariant is enforced by the
type rather than by each constructor remembering to raise, because "the
constructor remembers" is the very shape this lane deletes.

Spec grounding: pinned AdCP 3.1.1,
``dist/schemas/3.1.1/core/push-notification-config.json`` -- ``url`` is
required at top level; ``authentication`` is optional but, when present,
requires ``schemes`` and ``credentials``; ``AuthenticationScheme`` is
``["Bearer", "HMAC-SHA256"]``. The schema is SILENT on refusing a
credential-less HMAC registration at ingest -- the same standing as the SSRF
gate -- so this refusal is production-authoritative behavior, ungraded by any
conformance storyboard. Its shape (``VALIDATION_ERROR`` /
``recovery="correctable"`` / ``field``) is settled by the sibling URL gate, and
the recovery value derives from the SDK's bundled pinned
``adcp/_schemas/3.1/enums/error-code.json`` ``enumMetadata`` -- never from
``adcp.server.helpers.STANDARD_ERROR_CODES``, which contradicts the pin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from adcp.types import AuthenticationScheme, ContextObject, PushNotificationConfig
from adcp.types.generated_poc.core.push_notification_config import Authentication

from src.core.exceptions import AdCPValidationError
from src.core.schema_helpers import to_push_notification_config
from src.core.security.webhook_egress import (
    DeliverableWebhookAuth,
    HmacSecretMissing,
    webhook_auth_for,
)
from src.core.webhook_validator import reject_unsafe_webhook_registration_url

logger = logging.getLogger(__name__)


class WebhookConfigColumns(TypedDict):
    """The persistable projection's exact shape.

    A TypedDict rather than ``dict[str, Any]`` on purpose: this projection exists
    so the persistence boundary does not destructure the value, and that boundary's
    whole thesis is "the type is the receipt". Handing it a bag of ``Any`` would
    trade three type-checked attribute reads for three string-keyed lookups, making
    a key typo a runtime ``KeyError`` instead of a mypy error.
    """

    url: str
    authentication_type: str | None
    authentication_token: str | None


def _construct_stored_config(document: dict[str, Any]) -> PushNotificationConfig:
    """Build the library model from a STORED document without validating it.

    ``model_construct`` skips validation — which is the point on this path, since a
    stored row was accepted under an older gate and must keep delivering — but it
    also does not build NESTED models, so a bare call would leave
    ``config.authentication`` as a raw dict. Every consumer would then need an
    is-it-a-dict branch, which is the shape this package deletes rather than
    spreads.

    So the nested block is constructed too. The value therefore ALWAYS holds
    properly-typed library models; what differs between ingest and rehydration is
    only whether the contents were VALIDATED, never whether they are typed.
    """
    fields = dict(document)
    auth_block = fields.get("authentication")
    if isinstance(auth_block, dict):
        fields["authentication"] = Authentication.model_construct(**auth_block)
    return PushNotificationConfig.model_construct(**fields)


@dataclass(frozen=True, slots=True)
class ValidatedWebhookRegistration:
    """A push-notification registration that passed BOTH ingest preconditions.

    Holding one of these is the receipt: the URL cleared the registration SSRF
    gate and the credential half resolved to something a sender can actually
    apply. :attr:`auth` is what the senders consume -- resolved once, here, by
    the same :func:`~src.core.security.webhook_egress.webhook_auth_for` the
    senders use, so ingest and delivery cannot answer "is this signed?"
    differently.

    It HOLDS the library ``PushNotificationConfig`` rather than re-declaring a
    subset of it, and that is not a stylistic preference. The first version of
    this type was a hand-rolled dataclass carrying ``url`` plus two flattened
    auth primitives -- 2 of the 4 fields the pinned schema defines
    (``dist/schemas/3.1.1/core/push-notification-config.json``: ``url``,
    ``operation_id``, ``token``, ``authentication``). It therefore silently DROPPED
    ``operation_id`` and ``token``, both of which carry echo obligations the seller
    MUST honour -- ``operation_id`` is graded by the conformance universal
    ``dist/compliance/3.1.1/universal/webhook-emission.yaml`` requirement 1, and
    the schema requires ``token`` echoed "verbatim in every webhook payload".
    A value that claims to receipt a document must not be a lossy projection of it;
    that is the same defect this package exists to remove, one level up.

    Composition rather than inheritance because this is a RECEIPT wrapping a
    validated document plus the auth resolved from it, not a new kind of config:
    the library model stays exactly the library model, and no field of it can be
    lost without deleting it from the SDK.
    """

    config: PushNotificationConfig
    auth: DeliverableWebhookAuth

    @property
    def url(self) -> str:
        """The registration URL as a PLAIN str.

        Coerced here rather than stored: the library field is a pydantic
        ``AnyUrl``, and a pydantic object reaching a SQLAlchemy ``String`` column
        raises ``StatementError`` at flush (gh-#1377). The wire type stops being a
        wire type at THIS boundary, once, instead of at every transport wrapper.
        """
        return str(self.config.url) if self.config.url is not None else ""

    @property
    def authentication_type(self) -> str | None:
        """The single requested scheme as a PLAIN str (never an enum member)."""
        auth_block = self.config.authentication
        if auth_block is None or not auth_block.schemes:
            return None
        return str(auth_block.schemes[0])

    @property
    def authentication_token(self) -> str | None:
        """The buyer's credential as a PLAIN str."""
        auth_block = self.config.authentication
        if auth_block is None or auth_block.credentials is None:
            return None
        return str(auth_block.credentials)

    @property
    def operation_id(self) -> str | None:
        """The buyer's correlation id, which the seller MUST echo in every payload.

        Preserved rather than projected away: ``webhook-emission.yaml`` req. 1 is a
        graded conformance requirement, and it explicitly forbids recovering this by
        parsing the receiver URL -- so if the registration does not carry it, it is
        unrecoverable.
        """
        return str(self.config.operation_id) if self.config.operation_id is not None else None

    @property
    def token(self) -> str | None:
        """The buyer's validation token, which the seller MUST echo verbatim."""
        return str(self.config.token) if self.config.token is not None else None

    @classmethod
    def from_stash(
        cls,
        stashed: Any,
        *,
        field_prefix: str = "push_notification_config",
        context: ContextObject | dict[str, Any] | None = None,
    ) -> ValidatedWebhookRegistration:
        """Rehydrate a STORED registration — deliberately NOT a fresh ingest.

        This does NOT run the stash through the schema, and that is the whole
        point. Ingest validates against the pinned model because a buyer is there
        to correct what it rejects. A stored row has no buyer left: it was accepted
        under whatever gate existed when it was written, it DELIVERS today, and the
        delivery path fails closed (``context_manager`` catches
        ``AdCPValidationError`` and skips the webhook). So validating here does not
        protect anyone — it silently converts "delivered" into "never delivered at
        all", which is the exact failure this package exists to remove, arriving
        from the far end.

        That is not theoretical. Rows written through the untyped A2A path carry any
        scheme spelling and any credential length: measured, routing rehydration
        through the model stopped FIVE shapes delivering that deliver today — a
        sub-32-character credential, a non-canonical spelling like ``hmac-sha256``,
        an unrecognised scheme such as ``Basic``, a short ``token`` or a malformed
        ``operation_id`` (fields the old gate simply ignored), and an empty
        ``schemes`` list.

        What IS still enforced is the one thing that was never deliverable:
        ``HMAC-SHA256`` with no usable secret resolves to
        :class:`HmacSecretMissing`, and a value can never hold that — such a row
        refused before this package existed and must keep refusing, by name.

        The stored document is carried in the library type via ``model_construct``
        (no validation) rather than a hand-rolled shape, so nothing is dropped and
        the value still holds exactly one representation of a registration.
        """
        document = _normalize_legacy_stash(stashed)
        if not isinstance(document, dict):
            raise AdCPValidationError(
                f"Invalid {field_prefix}: stored registration is not an object.",
                field=field_prefix,
                suggestion="Re-register the webhook; the stored configuration is unreadable.",
                context=context,
            )

        url = str(document.get("url") or "").strip()
        if not url:
            raise AdCPValidationError(
                f"Invalid {field_prefix}.url: stored registration has no URL.",
                field=f"{field_prefix}.url",
                suggestion="Re-register the webhook with a URL.",
                context=context,
            )

        auth_block = document.get("authentication")
        schemes = auth_block.get("schemes") if isinstance(auth_block, dict) else None
        scheme = str(schemes[0]) if isinstance(schemes, list) and schemes else None
        credentials = auth_block.get("credentials") if isinstance(auth_block, dict) else None

        resolved = webhook_auth_for(scheme, credentials)
        if isinstance(resolved, HmacSecretMissing):
            field = f"{field_prefix}.authentication.credentials"
            raise AdCPValidationError(
                f"Invalid {field}: the stored registration asks for {scheme!r} but holds no "
                f"shared secret, so it can never be delivered — the receiver would reject "
                f"every unsigned request.",
                field=field,
                suggestion="Re-register the webhook supplying authentication.credentials.",
                context=context,
            )

        return cls(config=_construct_stored_config(document), auth=resolved)

    def to_columns(self) -> WebhookConfigColumns:
        """The persistable projection: exactly the columns a config row stores.

        The value knows which columns it becomes, so the repository never has to
        destructure it. That is not only cohesion — reading
        ``registration.authentication_type`` / ``.authentication_token`` at a call
        site is precisely the shape
        ``tests/unit/test_architecture_no_inline_webhook_auth_resolution.py``
        forbids, because it is how three senders each grew their own answer to
        "is this signed?". Projecting here (off ``self``) keeps the columns in one
        place and leaves no credential read at the persistence call site.
        """
        return WebhookConfigColumns(
            url=self.url,
            authentication_type=self.authentication_type,
            authentication_token=self.authentication_token,
        )

    def to_stash(self) -> dict[str, Any]:
        """Serialize for ``workflow_steps.request_data["push_notification_config"]``.

        Emits the WIRE shape — the same one
        ``PushNotificationConfig.model_dump(mode="json")`` writes — because this
        key already has other producers this lane does not convert
        (``media_buy_update`` stashes the whole request model,
        ``creatives/_workflow`` stashes the config object) and rows written
        before a deploy are wire-shaped too. One shape means the generic reader
        in :mod:`src.core.context_manager` can rehydrate ALL of them through
        :func:`from_stash`, instead of each producer needing its own parser.

        The ``authentication`` block is OMITTED when there is no scheme rather
        than emitted as ``{"schemes": [None], "credentials": None}``: both
        rehydrate identically, but only the omitting form is byte-identical to
        the library dump, and byte-identity is the whole point of "one shape".

        NOTHING is projected away: this dumps the held library model, so
        ``operation_id`` and ``token`` survive into the stash along with ``url``
        and ``authentication``. An earlier version rebuilt the dict from three
        flattened fields and silently dropped the other two — including
        ``operation_id``, whose echo is graded by
        ``dist/compliance/3.1.1/universal/webhook-emission.yaml`` req. 1 and which
        that requirement forbids recovering from the URL.

        Dumping the model also makes the byte-identity claim STRUCTURAL rather
        than hand-maintained: this IS ``model_dump(mode="json")`` of the same
        library type the other producers stash, so the shapes cannot drift apart
        by someone editing a literal here.
        """
        return self.config.model_dump(mode="json", exclude_none=True)

    def __post_init__(self) -> None:
        # Belt to the annotation's braces: mypy already refuses HmacSecretMissing
        # here, and this stops a dynamically-built value from laundering one past
        # a constructor at runtime.
        if isinstance(self.auth, HmacSecretMissing):
            raise AssertionError(
                "ValidatedWebhookRegistration cannot hold HmacSecretMissing -- "
                "the accept_* constructors raise AdCPValidationError instead."
            )


def _accept(
    *,
    config: PushNotificationConfig,
    field_prefix: str,
    context: ContextObject | dict[str, Any] | None,
) -> ValidatedWebhookRegistration:
    """Run both preconditions, then build the value. The ONE gate body.

    Absorbed verbatim from ``webhook_validator.reject_invalid_webhook_registration``
    so that removing that public reject-shaped gate changes no wording a buyer
    sees -- ``tests/integration/test_webhook_hmac_credentials_ingest_refusal.py``
    and ``tests/helpers/webhook_credential_refusal.py`` grade exactly this text
    and that a credential refusal is not mislabelled as a URL refusal.
    """
    url = str(config.url) if config.url is not None else None
    reject_unsafe_webhook_registration_url(url, field=f"{field_prefix}.url", context=context)

    auth_block = config.authentication
    scheme = str(auth_block.schemes[0]) if auth_block is not None and auth_block.schemes else None
    credentials = str(auth_block.credentials) if auth_block is not None and auth_block.credentials is not None else None
    resolved = webhook_auth_for(scheme, credentials)
    if isinstance(resolved, HmacSecretMissing):
        field = f"{field_prefix}.authentication.credentials"
        raise AdCPValidationError(
            f"Invalid {field}: authentication scheme {scheme!r} requires a shared secret, "
            f"but no credentials were supplied. A webhook registered for HMAC-SHA256 with no "
            f"secret can never be delivered -- the receiver would reject every unsigned request.",
            field=field,
            suggestion=(
                "Supply the shared secret in authentication.credentials, or remove the "
                "authentication block to receive unsigned webhooks."
            ),
            context=context,
        )

    return ValidatedWebhookRegistration(config=config, auth=resolved)


def accept_push_notification_primitives(
    url: str | None,
    scheme: str | None,
    credentials: str | None,
    *,
    token: str | None = None,
    field_prefix: str = "push_notification_config",
    context: ContextObject | dict[str, Any] | None = None,
) -> ValidatedWebhookRegistration:
    """Accept a registration already destructured into primitives.

    For the A2A protobuf shape, whose ``authentication`` carries a SINGULAR
    free-form ``scheme`` string rather than the tool path's ``schemes`` list, and
    which also carries ``token`` — passed through here so the value keeps it, since
    the pinned schema requires the seller to echo it verbatim in every payload.

    The URL gate runs BEFORE the model is built, deliberately: a blocked-but-
    well-formed URL (a metadata address, say) is a valid ``uri`` to pydantic, and
    refusing it here keeps the buyer's answer ``AdCPBlockedUrlError`` naming
    ``{prefix}.url`` rather than a generic parse failure.

    The scheme is normalized to its canonical enum spelling when it matches
    case-insensitively. That preserves what this path accepts today — the A2A
    push-config endpoint stores a free-form protobuf string, so lowercase rows
    exist in production and ``webhook_auth_for`` has always compared
    case-insensitively — while still producing a schema-valid library model. It
    also improves what gets STORED, since the row now carries the pinned spelling.
    """
    reject_unsafe_webhook_registration_url(url, field=f"{field_prefix}.url", context=context)

    authentication: dict[str, Any] | None = None
    if scheme is not None or credentials is not None:
        authentication = {"schemes": [_canonical_scheme(scheme)], "credentials": credentials}

    return _accept(
        config=_coerce_primitives_to_config(
            {"url": url, "token": token, "authentication": authentication},
            field_prefix=field_prefix,
        ),
        field_prefix=field_prefix,
        context=context,
    )


def _canonical_scheme(scheme: str | None) -> str | None:
    """The pinned enum spelling for a free-form protobuf scheme, if one matches."""
    if scheme is None:
        return None
    for member in AuthenticationScheme:
        if str(member).lower() == scheme.strip().lower():
            return str(member)
    return scheme


def _coerce_primitives_to_config(
    document: dict[str, Any],
    *,
    field_prefix: str,
) -> PushNotificationConfig:
    """Build the library model from the A2A protobuf primitives.

    Uses the same funnel the transport wrappers use, so this path cannot drift
    into its own validation dialect, and a refusal names the same field path.
    """
    coerced = to_push_notification_config(
        {key: value for key, value in document.items() if value is not None},
        field_prefix=field_prefix,
    )
    assert coerced is not None  # a non-empty dict always coerces or raises
    return coerced


def _normalize_legacy_stash(stashed: Any) -> Any:
    """Reduce a legacy multi-scheme stash to what it ALREADY delivered as.

    Strict at ingest, tolerant at rehydration -- and the asymmetry is principled,
    not a loophole. At ingest there is a buyer holding a request who can be told
    to pick one scheme, and refusing prevents an undeliverable registration from
    being stored. At rehydration there is no buyer left: the row was accepted
    long ago, a refusal surfaces to nobody, and the only effect would be to stop
    a webhook that delivers today. That is accept-then-never-deliver arriving
    from the other end -- the exact failure this epic exists to remove.

    Crucially this changes NOTHING about what such a row delivers. Before this
    lane the gate resolved auth with ``webhook_auth_for(schemes[0], creds)``;
    narrowing here reproduces that byte for byte. Only CARDINALITY is tolerated:
    the credential precondition still runs on the surviving scheme, so a
    credential-less HMAC row is still refused. And it warns, so the operator
    sees it.

    Such rows can exist: only the untyped A2A tool path could have written one,
    and lane 2 proved that path live. New rows cannot -- ``to_stash`` emits a
    single-element list and ingest now refuses multi-scheme outright.
    """
    if not isinstance(stashed, dict):
        return stashed
    auth = stashed.get("authentication")
    if not isinstance(auth, dict):
        return stashed
    schemes = auth.get("schemes")
    if not isinstance(schemes, list) or len(schemes) <= 1:
        return _drop_undeliverable_auth_block(stashed)

    logger.warning(
        "Legacy stashed webhook registration requested %d authentication schemes (%s); "
        "delivering with %r, exactly as this registration has always been delivered. "
        "Multi-scheme registrations are refused at ingest (pinned AdCP 3.1.1 allows one).",
        len(schemes),
        ", ".join(repr(str(s)) for s in schemes),
        str(schemes[0]),
    )
    normalized = {**stashed, "authentication": {**auth, "schemes": [schemes[0]]}}
    return _drop_undeliverable_auth_block(normalized)


def _drop_undeliverable_auth_block(stashed: Any) -> Any:
    """Drop a legacy auth block that carries no usable credential, when — and ONLY
    when — that block already resolved to ``Unauthenticated`` before this lane.

    The pinned schema requires ``credentials`` whenever ``authentication`` is
    present, so a legacy row like ``{"schemes": ["Bearer"]}`` with no credential is
    schema-INVALID and the model refuses it. At ingest that refusal is right: the
    buyer is there to fix it. At rehydration it is not — such a row DELIVERED
    before, unauthenticated, because ``webhook_auth_for("Bearer", None)`` resolves
    to :class:`Unauthenticated`. Refusing it now would convert "delivered" into
    "never delivered at all" for a registration the seller already accepted, which
    is accept-then-never-deliver arriving from the other end.

    So the block is dropped, reproducing that exact outcome — and ONLY for schemes
    that resolved to ``Unauthenticated``. An ``HMAC-SHA256`` row with no secret is
    NOT dropped: it resolved to :class:`HmacSecretMissing`, i.e. it never delivered,
    and it must keep refusing with the same field it always did.
    """
    if not isinstance(stashed, dict):
        return stashed
    auth = stashed.get("authentication")
    if not isinstance(auth, dict) or auth.get("credentials"):
        return stashed

    schemes = auth.get("schemes") or []
    scheme = str(schemes[0]) if schemes else None
    if isinstance(webhook_auth_for(scheme, None), HmacSecretMissing):
        # Undeliverable and always was — leave it to be refused by name.
        return stashed

    logger.warning(
        "Legacy stashed webhook registration carries scheme %r with no credentials; "
        "delivering UNAUTHENTICATED, exactly as this registration has always been "
        "delivered. The pinned schema requires credentials alongside a scheme, so new "
        "registrations in this shape are refused at ingest.",
        scheme,
    )
    return {key: value for key, value in stashed.items() if key != "authentication"}


def accept_push_notification_config(
    config: Any,
    *,
    field_prefix: str = "push_notification_config",
    context: ContextObject | dict[str, Any] | None = None,
) -> ValidatedWebhookRegistration:
    """Accept a config-shaped registration, normalizing model-or-dict ONCE.

    The tool surfaces disagreed about the shape they held -- create had a dict,
    update a typed model, sync either -- and each grew its own little
    destructuring branch. Normalizing here is what lets them all call one
    constructor and stop having a shape opinion.

    Normalization goes through :func:`to_push_notification_config`, the SAME funnel
    the transport wrappers use, so the pinned schema does the structural refusing:
    ``schemes`` ``maxItems: 1`` rejects a multi-scheme registration, ``credentials``
    ``minLength: 32`` rejects a too-short secret, and the ``AuthenticationScheme``
    enum rejects an unknown spelling — each naming its own field path. Those rules
    are therefore ENFORCED BY THE SPEC ARTEFACT rather than restated here in
    hand-written checks that could drift from it.

    What remains genuinely ours is what the schema does NOT say: the registration
    SSRF gate on the URL, and the refusal of an ``HMAC-SHA256`` registration with no
    usable secret (the schema is silent on both — see the module docstring).
    """
    coerced = to_push_notification_config(config, field_prefix=field_prefix)
    if coerced is None:
        raise AdCPValidationError(
            f"Invalid {field_prefix}: expected a push notification config object.",
            field=field_prefix,
            suggestion="Supply a push_notification_config object with a url.",
            context=context,
        )
    return _accept(config=coerced, field_prefix=field_prefix, context=context)
