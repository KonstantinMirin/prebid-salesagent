"""The A2A-native push-config endpoint refuses an HMAC-SHA256 registration with no secret.

``AdCPRequestHandler.on_create_task_push_notification_config``
(``src/a2a_server/adcp_a2a_server.py``, the ``setTaskPushNotificationConfig``
method) is the SECOND ingest surface for a ``push_notification_config``, and it
does not pass through ``create_media_buy``: it gates the URL, then calls
``PushNotificationConfigUoW.upsert`` directly. A gate added only to the tool
path leaves this one accepting the unservable registration.

Two things are graded here, and the second is the reason this file exists
rather than a line in the tool-path suite:

1. The registration is REFUSED, correctably, naming
   ``push_notification_config.authentication.credentials``.
2. The refusal is not laundered into the URL refusal. The upsert call is
   wrapped in ``except ValueError as e: raise _invalid_params_from_ssrf_error(e)``,
   and that helper hardcodes ``field="push_notification_config.url"`` plus
   ``webhook_ssrf_suggestion()`` (the https wording). A credential precondition
   that surfaces as ``ValueError`` from inside the repository is therefore
   re-enveloped as an SSRF problem, and the buyer is told to fix a URL that is
   fine. ``assert_credentials_refusal_envelope`` fails on exactly that, so
   "refuse before the try, or raise a type the catch does not swallow" is
   graded rather than merely written down.

Wire shape: A2A-native endpoints translate the AdCP refusal into
``InvalidParamsError`` (-32602) carrying the two-layer AdCP envelope in
``data`` — that ``data`` dict IS the wire envelope this transport emits, and it
is what the assertion runs against (tests/CLAUDE.md Error Verification Policy:
assert on the wire envelope, never on a reconstructed exception). Same
translation the sibling URL gate already uses on this handler, pinned by
``tests/unit/test_protocol_webhook_ssrf.py::test_a2a_set_push_handler_rejects_metadata_url``.

Spec grounding is identical to the tool-path surface and is written out once in
``tests/integration/test_webhook_hmac_credentials_ingest_refusal.py``: pinned
AdCP 3.1.1, ``core/push-notification-config.json`` (``Authentication`` requires
``credentials``; the block's presence SELECTS legacy signing and forbids a
9421 fallback), storyboard UNGRADED.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from a2a.types import AuthenticationInfo, InvalidParamsError, TaskPushNotificationConfig

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler
from tests.factories.principal import PrincipalFactory
from tests.helpers.webhook_credential_refusal import assert_credentials_refusal_envelope

# Passes the registration SSRF gate that runs first, so the only possible
# refusal is about the credential.
_SAFE_URL = "https://buyer.example.com/hook"

# The two shapes a real A2A buyer can send. The protobuf ``AuthenticationInfo``
# has no null string: an omitted ``credentials`` arrives as ``""``, which the
# handler maps to ``None``. Both spellings of the scheme are reachable because
# the handler stores ``params.authentication.scheme`` VERBATIM from a free-form
# protobuf string — there is no enum to constrain it.
_UNSERVABLE_SCHEMES = [
    pytest.param("HMAC-SHA256", id="spec-cased-scheme"),
    pytest.param("hmac-sha256", id="lowercase-scheme"),
]


def _params(scheme: str, credentials: str = "") -> TaskPushNotificationConfig:
    return TaskPushNotificationConfig(
        url=_SAFE_URL,
        task_id="task-1",
        id="pnc-1",
        authentication=AuthenticationInfo(scheme=scheme, credentials=credentials),
    )


@contextlib.contextmanager
def _authenticated_handler() -> Iterator[tuple[AdCPRequestHandler, MagicMock]]:
    """A handler whose auth chain is stubbed and whose store is a working double.

    ``upsert`` is given a real ``(config, created)`` return value even in the
    refusal cases, and that is load-bearing rather than tidiness: an unset
    ``MagicMock`` unpacks into ``ValueError``, the handler's
    ``except ValueError -> _invalid_params_from_ssrf_error`` catch converts that
    into a URL-SSRF envelope, and the refusal assertions below would then be
    graded against a failure the test itself manufactured. With the double
    complete, a handler that does NOT refuse SUCCEEDS — so the red is
    "DID NOT RAISE", which is the fact under test.
    """
    handler = AdCPRequestHandler()
    identity = PrincipalFactory.make_identity(tenant_id="t1", principal_id="p1")
    tool_context = MagicMock()
    tool_context.tenant_id = identity.tenant_id
    tool_context.principal_id = identity.principal_id

    with (
        patch.object(handler, "_get_auth_token", return_value="tok"),
        patch.object(handler, "_resolve_a2a_identity", return_value=identity),
        patch.object(handler, "_make_tool_context", return_value=tool_context),
        patch("src.a2a_server.adcp_a2a_server.PushNotificationConfigUoW") as uow,
    ):
        uow.return_value.__enter__.return_value.push_notification_configs.upsert.return_value = (MagicMock(), True)
        yield handler, uow


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", _UNSERVABLE_SCHEMES)
async def test_set_push_config_refuses_hmac_without_credentials(scheme: str) -> None:
    """The handler refuses, names the credentials field, and writes nothing."""
    with _authenticated_handler() as (handler, uow):
        with pytest.raises(InvalidParamsError) as exc_info:
            await handler.on_create_task_push_notification_config(_params(scheme), context=MagicMock())

        assert_credentials_refusal_envelope(exc_info.value.data, surface="setTaskPushNotificationConfig")
        uow.assert_not_called()


@pytest.mark.asyncio
async def test_set_push_config_accepts_hmac_with_credentials() -> None:
    """The control: a complete HMAC-SHA256 registration still reaches the store.

    Without it, a handler that refused every ``authentication`` block — or every
    registration — would satisfy the case above.
    """
    with _authenticated_handler() as (handler, uow):
        result = await handler.on_create_task_push_notification_config(
            _params("HMAC-SHA256", credentials="s" * 32), context=MagicMock()
        )

    assert result.authentication.scheme == "HMAC-SHA256"
    uow.assert_called_once_with("t1")
