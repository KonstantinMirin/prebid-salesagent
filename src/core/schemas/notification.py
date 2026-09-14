"""Webhook registration schemas: one ``Authentication`` concept, two pinned strictnesses.

The pin spells the legacy ``authentication`` object inline in two schemas,
``core/notification-config.json`` and ``core/push-notification-config.json``, with no shared
``$ref``, so codegen emits two classes with the same two fields (``schemes``,
``credentials``). Pydantic validates a model-typed slot by INSTANCE, so an instance of one
generated class is refused where the other is declared. That is how ``sync_accounts``,
handing a ``NotificationConfig``'s block to the registration gate that validates a
``PushNotificationConfig``, came to refuse every authenticated registration
(salesagent-3cs7o.12, item 1).

The two pins also differ on one axis: ``credentials`` is optional in
``notification-config.json`` and required in ``push-notification-config.json``. Neither a
dump in the caller nor a class that subclasses both with the requiredness decided by base
order is acceptable: the first is the mid-flow second representation pattern 4 bans, the
second misrepresents one pin through a hidden declaration. So the two strictnesses are a
TYPE RELATION, one concept with a narrowing subtype:

* :class:`Authentication` extends the notification-config spelling and declares nothing:
  ``credentials`` optional, as that pin says. Every site that only reads a block types it
  this way.
* :class:`PushAuthentication` extends :class:`Authentication` and the push-config spelling,
  and redeclares ``credentials`` as required, as that pin says. It is the sanctioned
  redeclaration (a narrowing, optional to required), and an instance is an instance of both
  generated classes. ``src/core/security/webhook_egress.py`` constructs it where a
  credential is needed to sign; a block with no credential is an undeliverable outcome there.

The local config models narrow their slot accordingly. ``PushNotificationConfig`` adopts a
base-typed block by rebuilding the subtype from the block's own two fields, so a
``NotificationConfig``'s block reaches the registration gate without a dump and is held to
the push pin's requiredness at the pin's own pointer (``authentication.credentials``).

Wire effect: the account-level path keeps optional credentials (a credential-less block on
``accounts[i].notification_configs[j]`` is not an INVALID_REQUEST); the push path keeps them
required.
"""

from typing import Any

from adcp.types import NotificationConfig as LibraryNotificationConfig
from adcp.types import PushNotificationConfig as LibraryPushNotificationConfig
from adcp.types.generated_poc.core.notification_config import Authentication as LibraryNotificationAuthentication
from adcp.types.generated_poc.core.push_notification_config import Authentication as LibraryPushAuthentication
from pydantic import Field, field_validator

__all__ = ["Authentication", "NotificationConfig", "PushAuthentication", "PushNotificationConfig"]


class Authentication(LibraryNotificationAuthentication):
    """The legacy ``authentication`` block as ``core/notification-config.json`` declares it.

    Declares nothing: ``schemes`` is required and ``credentials`` optional, inherited. The
    base of the concept; :class:`PushAuthentication` is its narrowing.
    """


class PushAuthentication(Authentication, LibraryPushAuthentication):
    """The same block as ``core/push-notification-config.json`` declares it: ``credentials`` required.

    A narrowing subtype: an instance is an :class:`Authentication` and an instance of both
    generated classes. The one redeclaration tightens the base's optional ``credentials`` to
    required, with the parent's own ``minLength: 32`` and description restated.
    """

    credentials: str = Field(
        min_length=32,
        description=LibraryPushAuthentication.model_fields["credentials"].description,
    )


class NotificationConfig(LibraryNotificationConfig):
    """The pinned ``core/notification-config.json``, with its block narrowed to the base class."""

    # The sanctioned redeclaration: narrowed to a local subclass, same nullability, same
    # default, the parent's own description.
    authentication: Authentication | None = Field(
        default=None, description=LibraryNotificationConfig.model_fields["authentication"].description
    )


class PushNotificationConfig(LibraryPushNotificationConfig):
    """The pinned ``core/push-notification-config.json``, with its block narrowed to the subtype."""

    authentication: PushAuthentication | None = Field(
        default=None, description=LibraryPushNotificationConfig.model_fields["authentication"].description
    )

    @field_validator("authentication", mode="before")
    @classmethod
    def _narrow_base_block(cls, v: Any) -> Any:
        """Adopt a base-typed block by rebuilding the subtype from its own two fields.

        ``sync_accounts`` hands a ``NotificationConfig``'s block, an :class:`Authentication`,
        to the registration gate, which validates this model. Pydantic refuses a base instance
        in a subtype slot, so the block is handed back as its two fields for the subtype to
        validate: a model-to-model step, never a dump, and the push pin's required
        ``credentials`` is refused by the subtype at ``authentication.credentials``, the same
        pointer a wire dict earns.
        """
        if isinstance(v, Authentication) and not isinstance(v, PushAuthentication):
            return {"schemes": v.schemes, "credentials": v.credentials}
        return v
