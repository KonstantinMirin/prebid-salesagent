"""One auth contract for every webhook sender, graded against real origins.

salesagent-47n9.24 (GH #1893, #1894). ``salesagent-47n9.1`` converged the
TRANSPORT — every sender dials through ``src.core.security.outbound_http`` and
``json=`` is unreachable from a signing sender. What did not converge is the
AUTH DECISION above it: three senders still answer "is this delivery signed,
and with what" three different ways, and two of them answer it wrongly.

The contract, stated once, is the one ``order_approval_service`` already keeps
(salesagent-47n9.20, graded in ``tests/integration/test_order_approval_webhook.py``):

1. The stored ``(authentication_type, authentication_token)`` pair becomes an
   auth decision in exactly ONE place — ``webhook_auth_for``.
2. A row that asked for ``HMAC-SHA256`` and has no usable secret DELIVERS
   NOTHING. Never unsigned. A buyer who asked for a signature will reject an
   unsigned POST, so sending one is strictly worse than sending none.
3. Signing is gated by the SCHEME, not by "is some credential lying around".
4. Scheme comparison is case-insensitive, because both spellings are rows a
   real buyer can produce (the A2A ``setTaskPushNotificationConfig`` handler
   stores ``params.authentication.scheme`` verbatim from a free-form protobuf
   string; ``media_buy_create`` stores the pinned enum spelling
   ``AuthenticationScheme = ["Bearer", "HMAC-SHA256"]`` @ AdCP 3.1.1).

Every case here is RED until each sender routes its decision through
``webhook_auth_for``. They must go green by CONVERGING on that resolver, not by
repairing the inline copies — repairing them in place makes each the fourth
divergent copy, which is the disease itself.

Why zero-hits is the discriminating assertion and not merely a small number:
each origin below is programmed to answer 200. A destination that would have
ACCEPTED the delivery is what makes "no request arrived" mean *the sender
refused*, rather than *the request went out and failed on arrival* — the
reading an origin programmed to reject would leave open. The same rationale is
written at ``test_order_approval_webhook.py::TestHmacSigning``.

Why these are integration tests and not BDD scenarios: neither sender runs
inside a request/response cycle. ``ProtocolWebhookService.send_notification``
is driven by the delivery scheduler and ``WebhookDeliveryService`` by the
delivery poller, both after the buyer's call has already returned — there is no
wire envelope for a ``Then`` step to assert on. The identical rationale is
already recorded for the sibling senders at
``tests/bdd/features/local-egress-ssrf-refusal.feature:45-51`` and in
``test_order_approval_webhook.py``'s module docstring.
"""

from __future__ import annotations

import pytest

from tests.harness import CircuitBreakerEnv, ProtocolWebhookEnv
from tests.helpers import SIGNATURE_HEADER, assert_signature_verifies_over_wire_body

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The pinned AdCP 3.1.1 enum spelling (``AuthenticationScheme``), which is what
# every writer in ``src/`` actually persists. Written as a constant because a
# regression that changed the spelling production compares against must fail
# these cases rather than be silently re-typed into them.
HMAC_SCHEME = "HMAC-SHA256"
BEARER_SCHEME = "Bearer"

# Any credential a buyer might store. There is deliberately no length
# requirement to satisfy: the 32-char strength gate was deleted with the inline
# resolver (salesagent-47n9.24) — it tested a column with no writers, so it had
# never once fired, and re-pointing it at authentication_token would have taken
# short-credential buyers from "delivered" to "not delivered at all".
STRONG_SECRET = "buyer-shared-secret"


def _assert_delivered_without_a_signature(env: CircuitBreakerEnv | ProtocolWebhookEnv) -> None:
    """Assert exactly one request arrived and it carries no HMAC signature header.

    Named against ``SIGNATURE_HEADER`` — the same constant
    ``assert_signature_verifies_over_wire_body`` verifies against — so a header
    rename cannot leave this absence assertion passing vacuously against a name
    nothing emits any more.
    """
    assert env.delivery_attempts == 1
    assert SIGNATURE_HEADER not in env.last_delivery.headers, (
        f"a delivery that did not ask for HMAC-SHA256 carries {SIGNATURE_HEADER} — "
        f"signing is gated by the scheme, not by whether a credential exists"
    )


class TestProtocolWebhookServiceRefusesUnsignedHmac:
    """``protocol_webhook_service`` must refuse, not deliver unsigned (GH #1893).

    ``send_notification`` already resolves through ``webhook_auth_for``, but an
    ``HmacSecretMissing`` decision falls through to an unsigned delivery
    (``src/services/protocol_webhook_service.py:253-263``): the buyer asked for
    a signature and receives none, with no error on any surface.
    """

    async def test_hmac_without_credentials_delivers_nothing(self, integration_db):
        """An HMAC-SHA256 row with no credential stored sends NOTHING.

        RED today: production resolves ``HmacSecretMissing`` and then proceeds
        to ``prepare_signed_request(payload, None, headers)``, which serializes
        without signing and delivers — one hit, unsigned.
        """
        with ProtocolWebhookEnv() as env:
            env.set_http_status(200)
            config = env.make_config(authentication_type=HMAC_SCHEME, authentication_token=None)

            delivered = await env.send(config=config)

            assert env.delivery_attempts == 0
            assert delivered is False, "a refused delivery must not report success to its caller"

    async def test_hmac_with_credentials_still_signs(self, integration_db):
        """The refusal must not swallow the case that CAN be signed.

        Guards the obvious over-correction: refusing on the scheme rather than
        on the missing credential would stop signing every real HMAC row.
        """
        with ProtocolWebhookEnv() as env:
            env.set_http_status(200)
            config = env.make_config(authentication_type=HMAC_SCHEME, authentication_token=STRONG_SECRET)

            delivered = await env.send(config=config)

            assert delivered is True
            assert env.delivery_attempts == 1
            assert_signature_verifies_over_wire_body(env.last_delivery, STRONG_SECRET)


class TestWebhookDeliveryServiceResolvesAuthThroughTheResolver:
    """``webhook_delivery_service`` resolves auth inline, four ways wrong (GH #1894).

    ``_deliver_with_backoff`` (``src/services/webhook_delivery_service.py:490-505``)
    never calls ``webhook_auth_for``. It is the sole entry in
    ``test_architecture_no_inline_webhook_auth_resolution``'s allowlist; each
    case below grades one of the four defects that entry records.
    """

    def test_hmac_row_signs_from_the_column_writers_populate(self, integration_db):
        """Defect 3: the secret comes from ``authentication_token``, not ``webhook_secret``.

        AdCP 3.1.1 puts the shared secret in
        ``push_notification_config.authentication.credentials``, which every
        writer in ``src/`` persists to ``authentication_token``.
        ``webhook_secret`` has ZERO writers anywhere in ``src/``, so today's
        signing branch is unreachable for any row a buyer can actually create.

        RED today: ``getattr(config, "webhook_secret", None)`` is None for this
        row, so the delivery goes out unsigned and the signature assertion
        fails on a missing header.
        """
        with CircuitBreakerEnv(tenant_id="t1", principal_id="p1") as env:
            env.setup_default_data()
            env.make_webhook_config(auth_type=HMAC_SCHEME, auth_token=STRONG_SECRET)
            env.set_http_response(200)

            delivered = env.call_send(tenant_id="t1", principal_id="p1")

            assert delivered is True
            assert env.delivery_attempts == 1
            assert_signature_verifies_over_wire_body(env.last_delivery, STRONG_SECRET)

    def test_hmac_row_without_credentials_delivers_nothing(self, integration_db):
        """Defect 1: a weak-or-absent secret must refuse, never downgrade to unsigned.

        Today a secret failing ``_verify_secret_strength`` is discarded at
        WARNING level and delivery proceeds UNSIGNED — the same quiet failure
        salesagent-47n9.20 refused to commit one file over. The ticket's
        acceptance names the whole class: "an HMAC-configured delivery with no
        USABLE secret refuses on every sender, never delivers unsigned".

        RED today: one unsigned hit.
        """
        with CircuitBreakerEnv(tenant_id="t1", principal_id="p1") as env:
            env.setup_default_data()
            env.make_webhook_config(auth_type=HMAC_SCHEME, auth_token=None)
            env.set_http_response(200)

            delivered = env.call_send(tenant_id="t1", principal_id="p1")

            assert env.delivery_attempts == 0
            assert delivered is False, "a refused delivery must not report success to its caller"

    def test_a_bearer_row_is_delivered_unsigned(self, integration_db):
        """Defect 2: signing is gated by the SCHEME, not by a truthy credential.

        This row HAS a credential — ``authentication_token`` is set, and it is
        the very column the HMAC branch signs from. What must keep it unsigned is
        the SCHEME saying Bearer. A sender that asks "is a credential present"
        instead of "did this row ask for HMAC-SHA256" attaches HMAC headers to a
        receiver expecting a plain bearer POST.

        The stronger form of the original case: that one relied on a stray
        ``webhook_secret``, which is no longer reachable at all now that the
        column is abandoned, so it could no longer fail for the right reason.
        """
        with CircuitBreakerEnv(tenant_id="t1", principal_id="p1") as env:
            env.setup_default_data()
            env.make_webhook_config(auth_type=BEARER_SCHEME, auth_token="buyer-bearer-token")
            env.set_http_response(200)

            env.call_send(tenant_id="t1", principal_id="p1")

            _assert_delivered_without_a_signature(env)

    def test_a_spec_cased_bearer_row_carries_the_authorization_header(self, integration_db):
        """Defect 4: the bearer branch compares a case no writer produces.

        Production compares ``config.authentication_type == "bearer"``. The
        pinned enum is ``["Bearer", "HMAC-SHA256"]`` and ``media_buy_create``
        persists ``schemes[0]`` verbatim, so the branch never fires for a
        protocol-registered config — those buyers get no ``Authorization``
        header at all.

        RED today: no ``Authorization`` header on the wire.
        """
        with CircuitBreakerEnv(tenant_id="t1", principal_id="p1") as env:
            env.setup_default_data()
            env.make_webhook_config(auth_type=BEARER_SCHEME, auth_token="buyer-bearer-token")
            env.set_http_response(200)

            env.call_send(tenant_id="t1", principal_id="p1")

            assert env.delivery_attempts == 1
            assert env.last_delivery.headers["Authorization"] == "Bearer buyer-bearer-token"

    def test_a_lowercase_scheme_still_authenticates(self, integration_db):
        """Case-insensitivity is a property of the resolver, and must reach this sender.

        The A2A ``setTaskPushNotificationConfig`` handler stores the scheme
        verbatim from a free-form protobuf string with no enum guard, so
        lowercase rows exist in production. Both spellings must authenticate;
        this is the case a "just fix the casing to Bearer" repair would break,
        which is why the fix is the resolver and not a re-spelling.
        """
        with CircuitBreakerEnv(tenant_id="t1", principal_id="p1") as env:
            env.setup_default_data()
            env.make_webhook_config(auth_type="bearer", auth_token="buyer-bearer-token")
            env.set_http_response(200)

            env.call_send(tenant_id="t1", principal_id="p1")

            assert env.delivery_attempts == 1
            assert env.last_delivery.headers["Authorization"] == "Bearer buyer-bearer-token"
