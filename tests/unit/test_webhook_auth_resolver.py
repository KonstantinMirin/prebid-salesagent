"""``webhook_auth_for`` — the one place a stored webhook config becomes an auth decision.

Three senders resolve push-notification auth today, each inline, each picking
its own field and its own value spelling:

* ``order_approval_service._approval_webhook_headers`` compares lowercase
  ``"bearer"`` / ``"basic"``, and its HMAC branch reads ``config.webhook_secret``
  — a column with ZERO writers anywhere in ``src/``, so every real HMAC row
  takes its refusal branch.
* ``protocol_webhook_service`` compares spec-cased ``"Bearer"`` /
  ``"HMAC-SHA256"`` and reads ``authentication_token`` — the field AdCP 3.1.1
  actually specifies.
* ``webhook_delivery_service`` does a third thing again (deferred:
  salesagent-ywzz).

The resolver replaces the inline reads with one function over PRIMITIVES —
``webhook_auth_for(scheme: str | None, credentials: str | None) -> WebhookAuth``
— so it stays usable from the sites that build detached/transient configs and
so ``src/core/security/`` gains no edge into ``src/core/database/models``.

The return type is the point of the ticket, not an implementation detail. A
``str | None`` return collapses "no auth configured" with "HMAC-SHA256
configured but no credentials", and those two need OPPOSITE handling: the first
is a legitimate unsigned delivery, the second is a config no sender can serve.
Every call site would have to re-derive the difference from an ambiguous value
— which is exactly how the third divergent copy appeared. So the resolver
returns one of five TYPES:

    SignWithSecret(secret) | BearerToken(token) | BasicCredentials(token)
    | Unauthenticated | HmacSecretMissing

Types, not sentinel objects: ``SignWithSecret(secret)`` and
``BearerToken(token)`` carry data and are therefore constructors, and a union of
types is what lets a sender match exhaustively (and a type checker prove the
match is exhaustive). ``isinstance`` below encodes that contract.

Spec grounding — pinned AdCP 3.1.1 (``adcp==6.6.0``):
``dist/schemas/3.1.1/enums/authentication-scheme.json`` →
``AuthenticationScheme = ["Bearer", "HMAC-SHA256"]`` (read off the installed
SDK), and ``core/push-notification-config.json`` puts the shared secret in
``authentication.credentials``. What the spec does NOT define — case handling,
``basic``, and what to do when HMAC has no secret — is decided by production
(source hierarchy: schema silent → production authoritative), and each such
decision is justified at its case below rather than assumed.
"""

from __future__ import annotations

from typing import Any

import pytest

# 32 chars: the minimum ``Authentication.credentials`` length in the pinned
# schema, so every "has a secret" case here is a secret a buyer could really
# have registered.
_SECRET = "s" * 32
_TOKEN = "buyer-issued-token"


def _resolve(scheme: str | None, credentials: str | None) -> Any:
    """Call the resolver, importing it at call time.

    A module-level import of a function that does not exist yet turns every
    case in this file into a COLLECTION error, which reports as one red mark
    about the file rather than N red marks about the contract. Imported here so
    each case fails on its own, naming the decision it was asserting.
    """
    from src.core.security.webhook_egress import webhook_auth_for

    return webhook_auth_for(scheme, credentials)


def _variant(name: str) -> type:
    """The named ``WebhookAuth`` variant type, resolved at call time.

    Same reason as :func:`_resolve`: the five variants do not exist yet, and a
    module-level ``from ... import SignWithSecret, ...`` would collapse the
    whole file into one collection error instead of one failure per decision.
    """
    from src.core.security import webhook_egress

    return getattr(webhook_egress, name)


class TestHmacWithoutCredentialsIsItsOwnState:
    """The decision this whole ticket exists to make representable."""

    @pytest.mark.parametrize("credentials", [None, ""], ids=["none", "empty-string"])
    def test_hmac_without_credentials_resolves_to_hmac_secret_missing(self, credentials: str | None) -> None:
        """Not ``Unauthenticated`` — the two mean opposite things to a sender.

        ``Unauthenticated`` says "this buyer asked for nothing, send it plain".
        ``HmacSecretMissing`` says "this buyer asked for a signature we cannot
        produce". Collapsing them is what makes a sender deliver unsigned to a
        receiver that will reject it, with no error anywhere — and per the
        pinned schema's "precedence is a switch, not a fallback", unsigned is
        not even a legal downgrade once the authentication block is present.
        """
        result = _resolve("HMAC-SHA256", credentials)

        assert isinstance(result, _variant("HmacSecretMissing")), (
            f"HMAC-SHA256 with credentials={credentials!r} resolved to {result!r}; a sender that "
            f"cannot tell this apart from 'no auth configured' will deliver it unsigned"
        )
        assert not isinstance(result, _variant("Unauthenticated"))

    def test_hmac_with_credentials_resolves_to_sign_with_secret(self) -> None:
        """The secret comes from ``authentication.credentials`` — the AdCP 3.1.1 field."""
        result = _resolve("HMAC-SHA256", _SECRET)

        assert isinstance(result, _variant("SignWithSecret"))
        assert result.secret == _SECRET


class TestBearerAndBasic:
    """Header credentials, preserving what the two senders do today."""

    def test_bearer_with_token_resolves_to_bearer_token(self) -> None:
        result = _resolve("Bearer", _TOKEN)

        assert isinstance(result, _variant("BearerToken"))
        assert result.token == _TOKEN

    def test_bearer_without_credentials_resolves_to_unauthenticated(self) -> None:
        """Reference behaviour, not a new decision.

        Both existing senders gate the Authorization header on the token being
        truthy (``authentication_type == "Bearer" and authentication_token``)
        and fall through to an unsigned, unauthenticated send otherwise. There
        is no ``BearerTokenMissing`` in the closed set because no sender needs
        to refuse it: an unsigned delivery to a Bearer-configured receiver is a
        missing header, not a forged signature.
        """
        assert isinstance(_resolve("Bearer", None), _variant("Unauthenticated"))

    def test_basic_is_preserved_rather_than_dropped(self) -> None:
        """``basic`` is not an AdCP scheme, and it is still reachable.

        ``order_approval_service`` honours ``"basic"`` today, and the A2A
        push-config endpoint stores a free-form protobuf string, so a stored
        ``basic`` row is a row a real buyer can have created. Dropping it
        during "unification" would silently stop sending an Authorization
        header those buyers rely on — a regression inside the sender being
        fixed. Preserved deliberately, and recorded as non-spec.
        """
        result = _resolve("basic", _TOKEN)

        assert isinstance(result, _variant("BasicCredentials"))
        assert result.token == _TOKEN


class TestSchemeComparisonIsCaseInsensitive:
    """Lowercase rows are real, and must resolve like their spec-cased spelling.

    The A2A ``setTaskPushNotificationConfig`` handler stores
    ``params.authentication.scheme`` VERBATIM from a free-form protobuf string
    — there is no enum on that path — and ``order_approval_service`` compares
    lowercase ``"bearer"`` today. An exact-enum comparison inside the resolver
    would therefore STOP sending Authorization for rows that get one today, and
    would let a lowercase HMAC row fall through to unsigned instead of
    ``HmacSecretMissing``. Case-insensitivity preserves current behaviour while
    deleting the divergence; it is a decision, so it is graded.
    """

    @pytest.mark.parametrize(
        ("scheme", "credentials", "variant"),
        [
            pytest.param("hmac-sha256", _SECRET, "SignWithSecret", id="lowercase-hmac-with-secret"),
            pytest.param("hmac-sha256", None, "HmacSecretMissing", id="lowercase-hmac-without-secret"),
            pytest.param("HMAC-Sha256", _SECRET, "SignWithSecret", id="mixed-case-hmac"),
            pytest.param("bearer", _TOKEN, "BearerToken", id="lowercase-bearer"),
            pytest.param("BEARER", _TOKEN, "BearerToken", id="uppercase-bearer"),
            pytest.param("Basic", _TOKEN, "BasicCredentials", id="capitalised-basic"),
        ],
    )
    def test_spelling_does_not_change_the_decision(self, scheme: str, credentials: str | None, variant: str) -> None:
        assert isinstance(_resolve(scheme, credentials), _variant(variant))


class TestNoSchemeConfigured:
    """Absence of a scheme is the ONE state that legitimately means "send plain"."""

    @pytest.mark.parametrize("credentials", [None, _TOKEN], ids=["no-credentials", "orphan-credentials"])
    def test_missing_scheme_resolves_to_unauthenticated(self, credentials: str | None) -> None:
        """Including the orphan-credentials row: per the pinned schema the
        ``authentication`` block selects the mode, so a stored credential with
        no scheme selects nothing and must not be guessed into one.
        """
        assert isinstance(_resolve(None, credentials), _variant("Unauthenticated"))

    def test_empty_scheme_resolves_to_unauthenticated(self) -> None:
        """``""`` is what the A2A protobuf path produces for an absent scheme."""
        assert isinstance(_resolve("", _TOKEN), _variant("Unauthenticated"))

    def test_unknown_scheme_resolves_to_unauthenticated(self) -> None:
        """An unrecognised scheme must not be treated as a signing request.

        Today no sender has a branch for it and it falls through to unsigned;
        the resolver keeps that. It must NOT resolve to ``HmacSecretMissing`` —
        that state is specifically "HMAC was asked for", and widening it would
        make senders refuse deliveries they complete today.
        """
        result = _resolve("Digest", _TOKEN)

        assert isinstance(result, _variant("Unauthenticated"))
        assert not isinstance(result, _variant("HmacSecretMissing"))
