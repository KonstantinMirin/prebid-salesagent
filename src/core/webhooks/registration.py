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

from dataclasses import dataclass
from typing import Any, TypedDict

from adcp.types import ContextObject

from src.core.exceptions import AdCPValidationError
from src.core.security.webhook_egress import (
    DeliverableWebhookAuth,
    HmacSecretMissing,
    webhook_auth_for,
)
from src.core.webhook_validator import reject_unsafe_webhook_registration_url


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


@dataclass(frozen=True, slots=True)
class ValidatedWebhookRegistration:
    """A push-notification registration that passed BOTH ingest preconditions.

    Holding one of these is the receipt: the URL cleared the registration SSRF
    gate and the credential half resolved to something a sender can actually
    apply. The three primitives are kept alongside :attr:`auth` because they
    are what persistence writes (columns), while :attr:`auth` is what the
    senders consume -- resolved once, here, by the same
    :func:`~src.core.security.webhook_egress.webhook_auth_for` the senders use,
    so ingest and delivery cannot answer "is this signed?" differently.
    """

    url: str
    authentication_type: str | None
    authentication_token: str | None
    auth: DeliverableWebhookAuth

    @classmethod
    def from_stash(
        cls,
        stashed: Any,
        *,
        field_prefix: str = "push_notification_config",
        context: ContextObject | dict[str, Any] | None = None,
    ) -> ValidatedWebhookRegistration:
        """Rehydrate a stashed registration by RE-RUNNING the ingest gate.

        Deliberately delegates to :func:`accept_push_notification_config` rather
        than parsing the stash itself. A stash is buyer-supplied data that has sat
        in a JSONB column, possibly across a deploy, possibly written by a producer
        that stores the wire shape directly -- so "trust the row" is exactly the
        assumption that let an unreceipted config reach a sender before.
        Re-running the gate means a stash that skipped one cannot become a value,
        and ingest and delivery still resolve auth through the same
        :func:`webhook_auth_for`.

        Callers at DELIVERY time must fail CLOSED on ``AdCPValidationError`` (skip
        that webhook), never let it escape: a validation error raised while
        updating a task's status must cost the webhook, not the transition.
        """
        return accept_push_notification_config(
            stashed,
            field_prefix=field_prefix,
            context=context,
        )

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

        Note the projection: the library ``PushNotificationConfig`` carries
        ``operation_id`` and ``token`` alongside ``url``/``authentication``, and
        this value carries neither, so a stash written from here drops them.
        No reader in ``src/`` reads either today; recorded so the lane that
        implements ``operation_id`` echo does not find it missing and guess why.
        """
        stashed: dict[str, Any] = {"url": self.url}
        if self.authentication_type is not None:
            stashed["authentication"] = {
                "schemes": [self.authentication_type],
                "credentials": self.authentication_token,
            }
        return stashed

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
    url: str | None,
    scheme: str | None,
    credentials: str | None,
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
    reject_unsafe_webhook_registration_url(url, field=f"{field_prefix}.url", context=context)

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

    return ValidatedWebhookRegistration(
        url=str(url) if url is not None else "",
        authentication_type=scheme,
        authentication_token=credentials,
        auth=resolved,
    )


def accept_push_notification_primitives(
    url: str | None,
    scheme: str | None,
    credentials: str | None,
    *,
    field_prefix: str = "push_notification_config",
    context: ContextObject | dict[str, Any] | None = None,
) -> ValidatedWebhookRegistration:
    """Accept a registration already destructured into primitives.

    For the A2A protobuf shape, whose ``authentication`` carries a SINGULAR
    free-form ``scheme`` string rather than the tool path's ``schemes`` list.
    """
    return _accept(
        url=url,
        scheme=scheme,
        credentials=credentials,
        field_prefix=field_prefix,
        context=context,
    )


def accept_push_notification_config(
    config: Any,
    *,
    field_prefix: str = "push_notification_config",
    context: ContextObject | dict[str, Any] | None = None,
) -> ValidatedWebhookRegistration:
    """Accept a config-shaped registration, normalizing model-or-dict ONCE.

    The three tool surfaces disagree about the shape they hold -- create has a
    ``dict``, update has a typed model, sync has either -- and each grew its own
    little destructuring branch. Normalizing here is what lets all three call
    one constructor and stop having a shape opinion.
    """
    if isinstance(config, dict):
        raw_url = config.get("url")
        auth_block: Any = config.get("authentication") or {}
        schemes = (auth_block.get("schemes") if isinstance(auth_block, dict) else None) or []
        creds = auth_block.get("credentials") if isinstance(auth_block, dict) else None
    else:
        raw_url = getattr(config, "url", None)
        auth_block = getattr(config, "authentication", None)
        schemes = getattr(auth_block, "schemes", None) or []
        creds = getattr(auth_block, "credentials", None)

    return _accept(
        # Library PushNotificationConfig.url is a pydantic AnyUrl, not a str.
        url=str(raw_url) if raw_url is not None else None,
        # schemes[0]: multi-scheme semantics against the pin are lane 3's
        # (typed-config-into-impl) spec-cite gate, deliberately unchanged here.
        scheme=schemes[0] if schemes else None,
        credentials=creds,
        field_prefix=field_prefix,
        context=context,
    )
