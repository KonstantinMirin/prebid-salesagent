"""What typing ``push_notification_config`` must NOT break.

Epic D lane C3 (salesagent-fo99.3). The lane types the config parameter all the
way into ``_impl`` and stops ``schemes[0]`` from swallowing a scheme. Both of
its two RED scenarios live in ``tests/bdd/features/local-egress-ssrf-refusal.feature``
(a >1 ``schemes`` array and a too-short ``credentials``, refused at ingest on
every wired transport). This file grades the other half of the change: the two
behaviors that PASS today, that nothing in the RED set would notice breaking,
and that the obvious implementation of the lane silently reverses.

1. THE LEGACY-TOLERANCE GUARD. A ``schemes`` array with two entries is
   schema-invalid against the pin (``core/push-notification-config.json``,
   ``maxItems: 1``), so the lane refuses it AT INGEST. Rows carrying one
   nevertheless exist: the untyped A2A tool path forwards the buyer's raw dict
   and ``schemes[0]`` accepted it silently. Making ``from_stash`` strict for
   symmetry would convert those rows from *delivered* into *never delivered* —
   a refusal at rehydration surfaces to nobody (the delivery path fails closed
   and continues), and the buyer is no longer there to correct anything. Strict
   at ingest, tolerant at rehydration is the split; this is its grader.

2. THE ROW-IDENTITY GUARD. ``push_notification_config.id`` is not a value field
   — it names the ROW to upsert. It reaches ``_impl`` today only because the A2A
   path forwards a raw dict; the AdCP model has no ``id`` field and is
   ``extra="ignore"``, so coercing the parameter DROPS it silently and every
   re-registration inserts a fresh row instead of updating the buyer's. Nothing
   type-checks that away and no refusal test can see it — the only observable is
   how many rows exist afterwards.

Why integration and not BDD: (1) is fired by a workflow-step status change after
the buyer's call has returned, so there is no wire envelope for a ``Then`` step
to assert on; (2) asserts on stored rows, not on a response. The identical
rationale is recorded at
``tests/integration/test_webhook_registration_reaches_delivery_signed.py`` and
``tests/bdd/features/local-egress-ssrf-refusal.feature``.

Both cases carry a reverse-TDD control, because both are GREEN today: a case
that cannot go red under the exact damage it exists to detect is grading
nothing.

MUST STAY GREEN untouched, and deliberately not modified here:
``tests/integration/test_webhook_registration_reaches_delivery_signed.py``,
``tests/integration/test_webhook_sender_auth_contract.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.exceptions import AdCPValidationError
from src.core.security.webhook_egress import (
    BasicCredentials,
    BearerToken,
    SignWithSecret,
    Unauthenticated,
)
from src.core.webhooks.registration import ValidatedWebhookRegistration, accept_push_notification_config
from tests.harness import MediaBuyPushRegistrationEnv
from tests.helpers import SIGNATURE_HEADER, assert_signature_verifies_over_wire_body

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

# The pinned AdCP 3.1.1 ``AuthenticationScheme`` spellings. Constants rather than
# literals per case: a regression that changed the spelling production compares
# against must fail these cases rather than be quietly re-typed into them.
HMAC_SCHEME = "HMAC-SHA256"
BEARER_SCHEME = "Bearer"

# At least 32 characters, because these registrations are made through the real
# tool wire where the pinned ``credentials`` ``minLength: 32`` applies.
STRONG_SECRET = "buyer-shared-secret-32-chars-or-more"

# The row id the buyer names on the A2A path. Spelled like production's own
# generated ids (``pnc_<hex>``) so the case cannot pass because something
# special-cased a test-shaped string.
BUYER_ROW_ID = "pnc_lanec3rowidentity"


def _registration(*, row_id: str | None = None) -> dict[str, Any]:
    """A valid single-scheme HMAC registration, optionally naming its row."""
    config: dict[str, Any] = {
        "url": "https://buyer.example.com/hook",
        "authentication": {"schemes": [HMAC_SCHEME], "credentials": STRONG_SECRET},
    }
    if row_id is not None:
        config["id"] = row_id
    return config


def _seed(env: MediaBuyPushRegistrationEnv) -> tuple[Any, Any]:
    """Seed the create dependency chain ONCE and return what a request names.

    Once per env, not once per registration: the row-identity cases register
    twice against the same tenant, and re-seeding between them would collide on
    the product primary key — and, more to the point, a second tenant would make
    "one row exists" true for a reason that has nothing to do with the upsert.
    """
    _tenant, _principal, product, pricing_option = env.setup_media_buy_data()
    return product, pricing_option


def _register_over_a2a(env: MediaBuyPushRegistrationEnv, seeded: tuple[Any, Any], config: dict[str, Any]) -> Any:
    """Run a real create_media_buy over A2A, registering *config*.

    A2A and not MCP, and that is load-bearing for both cases here: the A2A skill
    handler pops ``push_notification_config`` and forwards the buyer's RAW DICT,
    which is the only path on which an ``id`` survives to ``_impl`` at all. An
    MCP-driven version of the row-identity case would assert nothing — the typed
    tool parameter has no ``id`` field to carry.
    """
    product, pricing_option = seeded
    return env.call_a2a(**env.minimal_create_kwargs(product, pricing_option, push_notification_config=config))


def _webhook_url_of(env: MediaBuyPushRegistrationEnv, config: dict[str, Any]) -> dict[str, Any]:
    """The registration with its URL pointed at this env's live origin."""
    return {**config, "url": env.webhook_url}


class TestLegacyMultiSchemeStashKeepsDelivering:
    """A stashed 2-scheme registration still delivers exactly as it does today.

    "Exactly as today" is asserted through what the buyer's endpoint receives,
    not through the stash's shape: the lane rewrites how the registration is
    represented, so any assertion about the intermediate form would have to be
    rewritten by the change it is supposed to be guarding.
    """

    def test_a_two_scheme_stash_still_delivers_signed_when_hmac_is_first(self, integration_db):
        """``["HMAC-SHA256", "Bearer"]`` delivers signed, as ``schemes[0]`` already did."""
        with MediaBuyPushRegistrationEnv() as env:
            _register_over_a2a(env, _seed(env), _webhook_url_of(env, _registration()))
            env.set_http_status(200)

            step = env.push_step("create_media_buy")
            env.widen_stashed_schemes(step, [HMAC_SCHEME, BEARER_SCHEME])
            env.complete_step(step)

            assert env.delivery_attempts == 1, (
                f"a legacy 2-scheme row produced {env.delivery_attempts} deliveries — rehydration "
                f"refused a row that delivers today, which costs the buyer the notification "
                f"with nobody left to correct it"
            )
            assert_signature_verifies_over_wire_body(env.last_delivery, STRONG_SECRET)

    def test_the_narrowing_is_positional_so_a_bearer_first_row_delivers_bearer(self, integration_db):
        """``["Bearer", "HMAC-SHA256"]`` delivers as Bearer — first entry, not "the HMAC one".

        The half that makes the case above a preservation guard rather than a
        preference. "Resolve the array to whichever entry we can sign" would keep
        the signed case green while CHANGING what this row delivers, and a stored
        row's delivery behavior is exactly what the tolerance exists to preserve.
        """
        with MediaBuyPushRegistrationEnv() as env:
            _register_over_a2a(env, _seed(env), _webhook_url_of(env, _registration()))
            env.set_http_status(200)

            step = env.push_step("create_media_buy")
            env.widen_stashed_schemes(step, [BEARER_SCHEME, HMAC_SCHEME])
            env.complete_step(step)

            assert env.delivery_attempts == 1, f"a legacy Bearer-first row produced {env.delivery_attempts} deliveries"
            assert env.last_delivery.headers.get("Authorization") == f"Bearer {STRONG_SECRET}", (
                f"Authorization={env.last_delivery.headers.get('Authorization')!r} — the first "
                f"scheme in the stored array is what this row has always been delivered as"
            )
            assert SIGNATURE_HEADER not in env.last_delivery.headers, (
                f"a Bearer-first row arrived carrying {SIGNATURE_HEADER} — the resolution stopped "
                f"being positional, so stored rows changed what they deliver"
            )

    def test_control_a_strict_rehydration_stops_the_legacy_row_delivering(self, integration_db):
        """Reverse-TDD: make ``from_stash`` strict and the tolerance case must go red."""
        with MediaBuyPushRegistrationEnv() as env:
            _register_over_a2a(env, _seed(env), _webhook_url_of(env, _registration()))
            env.set_http_status(200)

            step = env.push_step("create_media_buy")
            env.widen_stashed_schemes(step, [HMAC_SCHEME, BEARER_SCHEME])
            with env.rehydration_refuses_multi_scheme():
                env.complete_step(step)

            assert env.delivery_attempts == 0, (
                f"rehydration was made strict and the row STILL delivered ({env.delivery_attempts} "
                f"attempts) — the tolerance case above is not graded by the strictness it pins"
            )


class TestA2AReRegistrationUpsertsTheRowTheBuyerNamed:
    """``push_notification_config.id`` keys the upsert, so re-registration updates one row."""

    def test_re_registering_the_same_id_updates_the_same_row(self, integration_db):
        with MediaBuyPushRegistrationEnv() as env:
            config = _webhook_url_of(env, _registration(row_id=BUYER_ROW_ID))
            seeded = _seed(env)

            _register_over_a2a(env, seeded, config)
            _register_over_a2a(env, seeded, config)

            rows = env.persisted_config_rows()
            assert [row.id for row in rows] == [BUYER_ROW_ID], (
                f"re-registering the row the buyer named left {[row.id for row in rows]} — "
                f"the id did not reach the upsert, so every re-registration inserts a new row "
                f"and the buyer can no longer address the one they created"
            )

    def test_control_losing_the_row_identity_inserts_a_second_row(self, integration_db):
        """Reverse-TDD: drop the id between wrapper and ``_impl``; the case above must go red."""
        with MediaBuyPushRegistrationEnv() as env:
            config = _webhook_url_of(env, _registration(row_id=BUYER_ROW_ID))
            seeded = _seed(env)

            with env.wrapper_loses_the_row_identity():
                _register_over_a2a(env, seeded, config)
                _register_over_a2a(env, seeded, config)

            rows = env.persisted_config_rows()
            assert len(rows) == 2, (
                f"the row identity was dropped and only {len(rows)} row(s) exist — the case above "
                f"would stay green with the id gone, so it is not grading the upsert key"
            )
            assert BUYER_ROW_ID not in [row.id for row in rows], (
                f"the buyer's id survived a mutation that removes it: {[row.id for row in rows]}"
            )


class TestMultiSchemeIsRefusedAtIngestButToleratedAtRehydration:
    """The strict/tolerant split, graded from BOTH sides.

    Pinned AdCP 3.1.1 gives ``authentication.schemes`` ``{"minItems": 1,
    "maxItems": 1}`` and states "**Precedence is a switch, not a fallback** ... A
    seller MUST NOT sign the same webhook both ways", so a multi-entry array is
    schema-INVALID. Taking ``schemes[0]`` would drop the buyer's stated intent
    silently — a buyer sending ``["Bearer", "HMAC-SHA256"]`` with no credentials
    passed the credential precondition because only ``Bearer`` was inspected, and
    was then never delivered to. That is the swallow this lane is named for.

    On the transports the model refuses the document first (``maxItems``), so
    these cases exercise the gate DIRECTLY — which is the surface that still
    accepts a dict, for ``from_stash`` and for legacy shapes. Without them the
    refusal is reachable but ungraded, and a future edit could quietly restore
    ``schemes[0]`` with a green suite.
    """

    def test_ingest_refuses_a_multi_scheme_registration_by_name(self):
        registration = {
            "url": "https://buyer.example.com/hook",
            "authentication": {"schemes": ["Bearer", "HMAC-SHA256"], "credentials": "s" * 32},
        }

        with pytest.raises(AdCPValidationError) as refusal:
            accept_push_notification_config(registration)

        assert refusal.value.field == "push_notification_config.authentication.schemes", (
            f"a multi-scheme registration must be refused BY NAME so the buyer can pick one; "
            f"got field={refusal.value.field!r}"
        )
        assert refusal.value.recovery == "correctable", (
            "the buyer can fix this by choosing a single scheme, so it is correctable"
        )

    def test_rehydration_tolerates_the_same_document_and_delivers_as_before(self):
        """The other side of the split: a stored row must not stop delivering.

        Only the untyped path could have written such a row, and lane C2 proved
        that path live — so these rows can exist. At rehydration there is no buyer
        left to correct anything, and refusing would convert "delivered" into
        "never delivered at all", which is accept-then-never-deliver arriving from
        the other end. Narrowing reproduces exactly what the row delivered before.
        """
        stashed = {
            "url": "https://buyer.example.com/hook",
            "authentication": {"schemes": ["Bearer", "HMAC-SHA256"], "credentials": "s" * 32},
        }

        rehydrated = ValidatedWebhookRegistration.from_stash(stashed)

        assert rehydrated.authentication_type == "Bearer", (
            f"rehydration must resolve to schemes[0] — exactly what webhook_auth_for(schemes[0], ...) "
            f"produced before this lane — got {rehydrated.authentication_type!r}"
        )
        assert isinstance(rehydrated.auth, BearerToken), (
            f"the resolved auth must still be applied, not dropped; got {type(rehydrated.auth).__name__}"
        )


class TestStoredRegistrationsKeepDelivering:
    """Rehydration must never convert "delivered" into "never delivered at all".

    Ingest validates against the pinned schema because a buyer is there to correct
    what it rejects. A STORED row has no buyer left: it was accepted under whatever
    gate existed when it was written, it delivers today, and the delivery path fails
    CLOSED (``context_manager`` catches ``AdCPValidationError`` and skips the
    webhook). So a stricter rehydration does not protect anyone — it silently stops
    deliveries.

    Every shape below is one the untyped A2A path could have written, because it
    stashed the buyer's RAW dict: production code states as fact that "the A2A
    push-config endpoint stores a free-form protobuf string, so lowercase rows exist
    in production". Each was measured DELIVERING before the SDK-composition
    restructure, and each stopped when rehydration briefly routed through the model.
    This class is why that cannot regress silently again.
    """

    @pytest.mark.parametrize(
        ("label", "authentication", "extra", "expected_auth"),
        [
            ("sub-32 credential", {"schemes": ["Bearer"], "credentials": "short"}, {}, BearerToken),
            ("lowercase scheme", {"schemes": ["hmac-sha256"], "credentials": "s" * 32}, {}, SignWithSecret),
            ("unrecognised scheme", {"schemes": ["Basic"], "credentials": "s" * 32}, {}, BasicCredentials),
            ("short token field", {"schemes": ["Bearer"], "credentials": "s" * 32}, {"token": "abc"}, BearerToken),
            ("empty schemes list", {"schemes": [], "credentials": "x"}, {}, Unauthenticated),
            ("scheme without credential", {"schemes": ["Bearer"]}, {}, Unauthenticated),
        ],
    )
    def test_a_legacy_row_still_resolves_the_auth_it_always_did(
        self, label, authentication, extra, expected_auth
    ):
        stashed = {"url": "https://buyer.example.com/hook", "authentication": authentication, **extra}

        rehydrated = ValidatedWebhookRegistration.from_stash(stashed)

        assert isinstance(rehydrated.auth, expected_auth), (
            f"{label}: a stored registration that delivered as {expected_auth.__name__} now "
            f"resolves to {type(rehydrated.auth).__name__} — this row stops being delivered to, "
            f"with no buyer left to fix it"
        )

    def test_the_one_shape_that_never_delivered_still_refuses(self):
        """HMAC with no secret is the exception, and must stay one.

        It resolved to HmacSecretMissing before this package existed, i.e. it never
        delivered. Tolerating it would mean delivering unsigned to a receiver that
        will reject every unsigned request — the opposite failure.
        """
        stashed = {
            "url": "https://buyer.example.com/hook",
            "authentication": {"schemes": ["HMAC-SHA256"]},
        }

        with pytest.raises(AdCPValidationError) as refusal:
            ValidatedWebhookRegistration.from_stash(stashed)

        assert refusal.value.field == "push_notification_config.authentication.credentials", (
            f"the refusal must name the missing secret; got {refusal.value.field!r}"
        )
