"""Grades our webhook HMAC signer/verifier against AdCP's own conformance vectors.

Source: ``tests/fixtures/adcp_webhook_vectors_pinned/webhook-hmac-sha256.json``,
vendored from ``adcontextprotocol/adcp`` at the repo's pinned spec tag (v3.1.1
-- see ``docs/adcp-spec-version.md`` and that fixture dir's ``_refresh.py``).
This turns "we changed the code" into "the wire is proven against the spec's
own test data" -- independent of any local test's own (possibly wrong)
expectations (salesagent-47n9.18).

Scope boundary -- excluded on purpose, not by oversight:

- The ``duplicate-keys-conflicting-values`` entry in ``vectors``, and the
  entire ``signer_side.rejection_vectors`` / ``signer_side.positive_vectors``
  blocks, all grade the spec's duplicate-object-key MUST-reject rule. Neither
  ``src/core/security/webhook_egress.py`` nor ``src/services/webhook_verification.py``
  implements that check yet -- it is salesagent-47n9.19's scope, a sibling
  ticket. Wiring it here would leave a RED test at this task's close.
- ``secret_rejection_vectors``' two entropy vectors (all-zero, all-repeated-char)
  grade a SHOULD, not a MUST (spec text: "Implementations SHOULD reject
  well-known weak values"). Implementing that check was tried and reverted:
  it would reject ``"x" * 32``, which BR-UC-004's "Webhook credentials at
  minimum length - accepted" BDD scenario deliberately uses to pin the exact
  32-char MUST-accept boundary. Only the two MUST-level length vectors
  (31-byte, empty) are graded here; the entropy SHOULD is a separate,
  deliberately unscoped follow-up (avoids breaking a pinned BDD scenario for
  a task with no design-review atom).
- The signer (``prepare_signed_request``) only ever emits its own canonical
  compact-separator, ``ensure_ascii=True`` serialization of a payload dict --
  by the Core Invariant salesagent-47n9.1 established, it never signs
  externally-supplied raw bytes. So it can only be graded against the subset
  of ``vectors`` whose ``raw_body`` IS byte-reproducible from a dict via that
  exact serialization (pure-ASCII, compact-form vectors); vectors in other
  JSON forms (spaced, pretty-printed, unicode, empty-body, embedded nulls,
  trailing newline) are verifier-only -- there is nothing in the signer to
  grade them against. This is a scope boundary from the architecture, not a
  gap: the verifier (byte-transparent) is graded against every remaining
  vector regardless of form.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.security.webhook_egress import prepare_signed_request
from src.services.webhook_verification import WebhookVerificationError, WebhookVerifier

_VECTORS_PATH = Path(__file__).parent.parent / "fixtures" / "adcp_webhook_vectors_pinned" / "webhook-hmac-sha256.json"
_DATA = json.loads(_VECTORS_PATH.read_text())
_SECRET = _DATA["secret"]

_DUPLICATE_KEY_VECTOR_ID = "duplicate-keys-conflicting-values"  # salesagent-47n9.19 scope

_VERIFIER_ACCEPT_VECTORS = [v for v in _DATA["vectors"] if v["id"] != _DUPLICATE_KEY_VECTOR_ID]
assert len(_VERIFIER_ACCEPT_VECTORS) == 14, "expected 14 non-duplicate-key vectors in the pinned fixture"

# Pure-ASCII, compact-separator vectors our signer's canonical serialization
# byte-reproduces exactly -- see module docstring for the excluded forms.
_SIGNER_VECTOR_IDS = frozenset(
    {
        "compact-js-style",
        "empty-object",
        "nested",
        "scalars-mixed",
        "timestamp-zero",
        "timestamp-2040",
        "compact-whitespace-keys",
    }
)
_SIGNER_VECTORS = [v for v in _DATA["vectors"] if v["id"] in _SIGNER_VECTOR_IDS]
assert len(_SIGNER_VECTORS) == len(_SIGNER_VECTOR_IDS), "a signer-subset vector id is missing from the fixture"

_REJECTION_VECTORS = _DATA["rejection_vectors"]

# Only the two MUST-level (length) secret vectors -- see module docstring.
_SECRET_MUST_REJECT_VECTORS = [v for v in _DATA["secret_rejection_vectors"] if len(v["secret"]) < 32]
assert len(_SECRET_MUST_REJECT_VECTORS) == 2, "expected exactly the 31-byte and empty-string secret vectors"


class TestVerifierAcceptsSpecVectors:
    """Our verifier (``WebhookVerifier`` -> ``adcp.signing.webhook_hmac.verify_webhook_hmac``)
    must accept every non-duplicate-key vector's exact raw bytes + signature.

    ``time.time`` is patched to the vector's own timestamp so the replay-window
    check passes regardless of the vector's (often historical) timestamp --
    the property under test is signature validity over raw bytes, not clock
    freshness (that's graded separately by the rejection vectors below).
    """

    @pytest.mark.parametrize("vector", _VERIFIER_ACCEPT_VECTORS, ids=[v["id"] for v in _VERIFIER_ACCEPT_VECTORS])
    def test_accepts_vector(self, vector: dict) -> None:
        verifier = WebhookVerifier(webhook_secret=_SECRET, replay_window_seconds=300)
        with patch("src.services.webhook_verification.time.time", return_value=float(vector["timestamp"])):
            assert (
                verifier.verify_webhook(
                    body=vector["raw_body"].encode("utf-8"),
                    headers={
                        "X-AdCP-Signature": vector["expected_signature"],
                        "X-AdCP-Timestamp": str(vector["timestamp"]),
                    },
                )
                is True
            )


class TestVerifierRejectsMalformedOrTamperedRequests:
    """Our verifier must reject every ``rejection_vectors`` entry for its stated reason.

    Timing vectors (``timestamp-too-old``/``-future``) use the vector's own
    ``current_time`` as the patched ``now`` -- that is the point under test.
    Non-timing vectors pin ``now`` to the vector's own (numeric) ``timestamp``
    so the replay window does not mask the defect being graded; the one
    non-numeric-timestamp vector cannot supply a numeric ``now`` at all, so it
    uses an arbitrary fixed value (the defect fires before the window check
    can run).
    """

    @pytest.mark.parametrize("vector", _REJECTION_VECTORS, ids=[v["id"] for v in _REJECTION_VECTORS])
    def test_rejects_vector(self, vector: dict) -> None:
        now = vector.get("current_time")
        if now is None:
            ts = vector["timestamp"]
            now = ts if isinstance(ts, (int, float)) else 1700000000

        headers = {"X-AdCP-Timestamp": str(vector["timestamp"])}
        if vector["signature"] is not None:
            headers["X-AdCP-Signature"] = vector["signature"]

        verifier = WebhookVerifier(webhook_secret=_SECRET, replay_window_seconds=300)
        with patch("src.services.webhook_verification.time.time", return_value=float(now)):
            with pytest.raises(WebhookVerificationError):
                verifier.verify_webhook(body=vector["raw_body"].encode("utf-8"), headers=headers)


class TestVerifierRejectsWeakSecretsAtMustLevel:
    """``WebhookVerifier.__init__`` must reject secrets below the 32-char MUST floor.

    Only the length-based vectors are graded -- the entropy SHOULD (reject
    all-zero / all-repeated-char secrets) is a documented, deliberate
    exclusion; see the module docstring.
    """

    @pytest.mark.parametrize(
        "vector", _SECRET_MUST_REJECT_VECTORS, ids=[v["description"] for v in _SECRET_MUST_REJECT_VECTORS]
    )
    def test_rejects_short_secret(self, vector: dict) -> None:
        with pytest.raises(ValueError):
            WebhookVerifier(webhook_secret=vector["secret"])


class TestSignerReproducesSpecVectors:
    """Our signer (``prepare_signed_request`` -> ``adcp.sign_legacy_webhook``)
    must reproduce the exact wire bytes and signature for every vector whose
    raw body is our canonical (compact-separator, ASCII-escaped) form.
    """

    @pytest.mark.parametrize("vector", _SIGNER_VECTORS, ids=[v["id"] for v in _SIGNER_VECTORS])
    def test_signs_vector(self, vector: dict) -> None:
        payload = json.loads(vector["raw_body"])

        headers, body_bytes = prepare_signed_request(payload, _SECRET, {}, timestamp=vector["timestamp"])

        assert body_bytes == vector["raw_body"].encode("utf-8")
        assert headers["X-AdCP-Signature"] == vector["expected_signature"]
        assert headers["X-AdCP-Timestamp"] == str(vector["timestamp"])
