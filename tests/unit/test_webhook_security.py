"""Unit tests for webhook security features (SSRF protection and HMAC authentication)."""

import hashlib
import hmac
import json
import time

import pytest
from adcp.types import TaskType

from src.core.webhook_authenticator import WebhookAuthenticator
from src.core.webhook_validator import (
    WEBHOOK_TASK_TYPE_FALLBACK,
    WebhookURLValidator,
    validate_webhook_task_type,
)


class TestValidateWebhookTaskType:
    """Coercion of untrusted action labels to SDK-accepted TaskType values."""

    @pytest.mark.parametrize("valid", [m.value for m in TaskType])
    def test_valid_tasktype_returned_unchanged(self, valid):
        """Every TaskType enum member passes through verbatim."""
        assert validate_webhook_task_type(valid) == valid

    @pytest.mark.parametrize(
        "invalid",
        # media_buy_delivery is now a valid TaskType member (adcp 6.6 / spec 3.1.1), so it no
        # longer coerces to the fallback — dropped from the invalid-label set.
        ["delivery_report", "unknown", "", "not_a_task"],
    )
    def test_non_tasktype_coerced_to_fallback(self, invalid):
        """Non-members are coerced to the default fallback."""
        assert validate_webhook_task_type(invalid) == WEBHOOK_TASK_TYPE_FALLBACK
        assert WEBHOOK_TASK_TYPE_FALLBACK == "update_media_buy"

    def test_custom_fallback_honored(self):
        """The fallback is overridable for callers with a different default."""
        assert validate_webhook_task_type("bogus", fallback="sync_creatives") == "sync_creatives"

    def test_fallback_must_be_valid_caller_choice(self):
        """A valid label ignores the fallback entirely."""
        assert validate_webhook_task_type("sync_creatives", fallback="update_media_buy") == "sync_creatives"


class TestWebhookURLValidator:
    """Test SSRF protection in webhook URL validation.

    WebhookURLValidator is the REGISTRATION-time gate: validate_webhook_url_registration
    performs no DNS resolution, while the outbound/SEND-time gate lives on the egress seam
    (see the outbound-fetch tests). Both roles are graded here and there respectively.

    The ADDRESS cases below use ``https://`` so the address verdict is what they
    grade: the scheme is checked first (url_validator._scheme_error), so a plain-http
    fixture here would be refused for its scheme under the default posture and the
    ``10.0.0.0/8``-style assertions would stop grading the address policy at all.
    The scheme decision itself is graded on its own, in
    ``TestWebhookSchemeGateTracksTheEgressSeam``.

    POSTURE IS PINNED, and that is load-bearing. ``tests/conftest.py`` sets
    ``ADCP_TESTING=true`` autouse for the whole suite, and under it the gate
    hands any loopback verdict to ``_maybe_allow_localhost``, which RESCUES it.
    An address case left on the ambient posture would therefore grade the
    testing-mode allowance instead of the address policy it claims to grade —
    and the two loopback cases would flip from refused to accepted outright
    (verified: removing the fixture below fails exactly those two).
    The allowance is real behaviour and is graded on purpose, in
    ``TestLocalhostAllowanceUnderTestingMode`` below; here it is switched off so
    these cases mean what their names say.
    """

    @pytest.fixture(autouse=True)
    def _no_testing_mode(self, monkeypatch):
        """Grade the address policy, not the testing-mode loopback allowance."""
        monkeypatch.delenv("ADCP_TESTING", raising=False)

    def test_valid_public_https_url(self):
        """Valid public HTTPS URLs should pass."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://example.com/webhook")
        assert is_valid
        assert error == ""

    def test_blocks_localhost(self):
        """Should block localhost."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://localhost:3000/webhook")
        assert not is_valid
        assert "blocked" in error.lower()

    def test_blocks_127_0_0_1(self):
        """Should block 127.0.0.1, with a message that does not name the range."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://127.0.0.1:8080/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_private_network_10(self):
        """Should block 10.0.0.0/8 private network, with a message that does not name the range."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://10.0.0.5/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_private_network_192(self):
        """Should block 192.168.0.0/16 private network, with a message that does not name the range."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://192.168.1.1/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_private_network_172(self):
        """Should block 172.16.0.0/12 private network, with a message that does not name the range."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://172.16.0.1/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_link_local(self):
        """Should block 169.254.0.0/16 link-local (AWS metadata service), naming no range."""
        # Use a non-hostname-allowlist IP so the CIDR path is graded (169.254.169.254
        # is also in BLOCKED_HOSTNAMES and short-circuits before network match).
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://169.254.1.1/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_aws_metadata_hostname(self):
        """Literal metadata IP hostname is blocked by hostname allowlist."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(
            "https://169.254.169.254/latest/meta-data"
        )
        assert not is_valid
        assert "blocked" in error.lower()

    def test_blocks_metadata_hostname(self):
        """Should block cloud metadata hostnames."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(
            "https://metadata.google.internal/webhook"
        )
        assert not is_valid
        assert "blocked" in error.lower()

    @pytest.mark.parametrize("hatch_open", [True, False], ids=["hatch_open", "hatch_closed"])
    def test_requires_http_or_https(self, monkeypatch, hatch_open):
        """Should reject non-HTTP protocols — under either scheme posture.

        The hatch is set explicitly (both ways) because it selects the message:
        open it and the validator is in "http or https" mode, close it and it is
        in "HTTPS only" mode. A non-HTTP scheme is refused in both, which is what
        this grades; leaving the flag ambient would grade whichever one the shell
        happened to provide.
        """
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true" if hatch_open else "false")
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("ftp://example.com/webhook")
        assert not is_valid
        assert "http" in error.lower()

    def test_requires_hostname(self):
        """Should reject URLs without hostname."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https:///webhook")
        assert not is_valid
        assert "hostname" in error.lower()

    def test_invalid_url_format(self):
        """Should reject malformed URLs."""
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("not-a-url")
        assert not is_valid
        assert error != ""

    def test_blocks_cgnat_range(self):
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://100.64.1.1/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_multicast_range(self):
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://224.0.0.1/webhook")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_ipv6_multicast_range(self):
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://[ff02::1]/")
        assert not is_valid
        assert error == "URL resolves to a restricted range."

    def test_blocks_nat64_well_known_prefix(self):
        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("https://[64:ff9b::a9fe:a9fe]/")
        assert not is_valid
        assert error == "URL resolves to a restricted range."


class TestLocalhostAllowanceUnderTestingMode:
    """The loopback allowance is a real behaviour, so it is graded on BOTH arms.

    ``validate_webhook_url_registration`` hands its verdict to
    ``_maybe_allow_localhost``, which rescues a loopback refusal when
    ``ADCP_TESTING`` is set. That branch is what lets an e2e capture server on
    127.0.0.1 register at all — live production behaviour, and until now asserted
    NOWHERE: the only cases that touched it graded the NEGATIVE (that the
    allowance must not also rescue a bad SCHEME), and the two tests that reached
    it directly went through ``validate_for_testing``, which this change deletes.

    Both arms are pinned explicitly because the suite sets ``ADCP_TESTING=true``
    autouse: a one-armed test here would silently grade whichever posture the
    fixture happened to leave behind, which is exactly how a gate control goes
    inert without anyone noticing.

    The scheme hatch is opened because a loopback capture server is reached over
    plain http; that is the same pairing the e2e stack runs
    (``ADCP_OUTBOUND_ALLOW_INSECURE=true`` beside ``ADCP_TESTING=true``), and it
    keeps this class grading the ADDRESS allowance rather than colliding with the
    scheme gate graded below.
    """

    LOOPBACK_URLS = ["http://localhost:3001/webhook", "http://127.0.0.1:8080/webhook"]

    @pytest.mark.parametrize("url", LOOPBACK_URLS)
    def test_loopback_refused_without_testing_mode(self, monkeypatch, url):
        """Without ADCP_TESTING a loopback URL is refused, allowance or not."""
        monkeypatch.delenv("ADCP_TESTING", raising=False)
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true")

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(url)

        assert not is_valid, f"{url} must be refused when the testing-mode allowance is off"
        assert error != "", "a refusal must say something the caller can log"

    @pytest.mark.parametrize("url", LOOPBACK_URLS)
    def test_loopback_allowed_under_testing_mode(self, monkeypatch, url):
        """With ADCP_TESTING the allowance rescues the loopback verdict.

        This is the arm with no prior coverage. Verified to fail the moment
        ``_maybe_allow_localhost`` stops rescuing — without it, deleting that
        branch would break only the e2e stack, far from the change that caused it.
        """
        monkeypatch.setenv("ADCP_TESTING", "true")
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true")

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(url)

        assert is_valid, f"{url} must be accepted under ADCP_TESTING so a loopback capture server can register"
        assert error == ""

    def test_allowance_does_not_rescue_a_private_range(self, monkeypatch):
        """The allowance is loopback-only — a private range stays refused under it.

        Carried over from the deleted ``validate_for_testing`` coverage: the
        rescue re-derives loopback-ness structurally from the URL (see
        ``_maybe_allow_localhost``), so a 192.168/16 address — not loopback —
        must survive it. Without this, widening the rescue predicate would go
        unnoticed.
        """
        monkeypatch.setenv("ADCP_TESTING", "true")
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true")

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("http://192.168.1.1/webhook")

        assert not is_valid, "the loopback allowance must not rescue a private-range address"
        assert error == "URL resolves to a restricted range."


class TestWebhookSchemeGateTracksTheEgressSeam:
    """Ingest requires https on exactly the condition the SEND seam does.

    ``src/core/security/outbound_http.py`` ``_require_tls`` refuses anything but
    ``https://`` unless ``ADCP_OUTBOUND_ALLOW_INSECURE`` is open. Ingest used to
    require https only when ``is_production() and not ADCP_TESTING``, so in every
    non-production or ADCP_TESTING process a buyer's ``http://`` webhook URL was
    ACCEPTED at registration and then refused at every single send — a permanent,
    silent non-delivery, with no error at the one moment the buyer could have fixed
    the URL. These cases pin the two gates to one condition.

    Every case sets the hatch EXPLICITLY, never relying on it being unset:
    ``run_all_tests_host.sh`` exports ``ADCP_OUTBOUND_ALLOW_INSECURE=true`` and
    ``tox.ini`` forwards it, so an ambient value would otherwise disarm the
    rejection arms into a vacuous pass.
    """

    HTTP_URL = "http://buyer.example.com/hook"
    HTTPS_URL = "https://buyer.example.com/hook"

    # The one surviving gate. There were two until gh-#1589 deleted the
    # send-side twin (``validate_webhook_url``), which had no production callers
    # and existed only as a patch target. Kept as a list because the scheme
    # decision is a property of the GATE, not of this one method — if a second
    # ingest gate ever appears it belongs here rather than in a copy of these
    # cases. Resolves no DNS, so it stays hermetic.
    _GATES = [
        WebhookURLValidator.validate_webhook_url_registration,
    ]

    @staticmethod
    def _hatch(monkeypatch, *, open_: bool) -> None:
        monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true" if open_ else "false")

    @pytest.mark.parametrize("gate", _GATES, ids=lambda g: g.__name__)
    @pytest.mark.parametrize("environment", ["production", "development"])
    @pytest.mark.parametrize("adcp_testing", ["true", None], ids=["adcp_testing", "no_adcp_testing"])
    def test_plain_http_rejected_when_hatch_closed(self, monkeypatch, gate, environment, adcp_testing):
        """Plain http is refused in EVERY posture while the hatch is closed.

        Parametrised across ENVIRONMENT and ADCP_TESTING precisely because the
        scheme verdict must no longer depend on either of them — that dependency
        was the drift. ADCP_TESTING still buys a localhost/loopback allowance, but
        it does not buy plaintext: the two concerns stay separate.
        """
        monkeypatch.setenv("ENVIRONMENT", environment)
        if adcp_testing is None:
            monkeypatch.delenv("ADCP_TESTING", raising=False)
        else:
            monkeypatch.setenv("ADCP_TESTING", adcp_testing)
        self._hatch(monkeypatch, open_=False)

        is_valid, error = gate(self.HTTP_URL)

        assert not is_valid, f"{gate.__name__} accepted a plain-http webhook URL the send seam refuses"
        assert "https" in error.lower()

    def test_adcp_testing_localhost_allowance_does_not_reopen_plain_http(self, monkeypatch):
        """The loopback allowance and the scheme rule are separate concerns.

        ``ADCP_TESTING=true`` rescues a localhost/loopback ADDRESS verdict
        (``_maybe_allow_localhost``). It must not rescue the SCHEME verdict —
        collapsing the two would put http back in exactly the processes where
        the old bug lived. A capture server on loopback needs the hatch open,
        which is what the e2e stack sets.
        """
        monkeypatch.setenv("ADCP_TESTING", "true")
        self._hatch(monkeypatch, open_=False)

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration("http://localhost:3001/hook")

        assert not is_valid
        assert "https" in error.lower()

    @pytest.mark.parametrize("environment", ["production", "development"])
    def test_plain_http_accepted_when_hatch_open(self, monkeypatch, environment):
        """The hatch — and only the hatch — admits plain http, production included.

        The seam has no production carve-out either (``_require_tls`` reads the
        flag and nothing else), so neither does this. The hatch is what the e2e
        stack and ``run_all_tests_host.sh`` open for loopback capture servers.
        """
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.delenv("ADCP_TESTING", raising=False)
        self._hatch(monkeypatch, open_=True)

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(self.HTTP_URL)

        assert is_valid, f"hatch-open registration refused plain http: {error}"
        assert error == ""

    @pytest.mark.parametrize("hatch_open", [True, False], ids=["hatch_open", "hatch_closed"])
    @pytest.mark.parametrize("environment", ["production", "development"])
    def test_https_registration_accepted_in_every_posture(self, monkeypatch, environment, hatch_open):
        """https is always admissible — the hatch relaxes, it never tightens."""
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.delenv("ADCP_TESTING", raising=False)
        self._hatch(monkeypatch, open_=hatch_open)

        is_valid, error = WebhookURLValidator.validate_webhook_url_registration(self.HTTPS_URL)

        assert is_valid
        assert error == ""

    def test_ingest_and_seam_agree_on_the_scheme_verdict(self, monkeypatch):
        """The two gates are graded against each other, not against a copy of the rule.

        A restated env read in webhook_validator would satisfy every case above
        and still drift the day the seam's rule changes. This one asks BOTH
        implementations the same question and requires the same answer, so the
        shared condition is a property under test rather than a comment.
        """
        from src.core.security.outbound_http import OutboundRequestBlocked, _require_tls

        def seam_admits(url: str) -> bool:
            try:
                _require_tls(url)
            except OutboundRequestBlocked:
                return False
            return True

        for hatch_open in (False, True):
            self._hatch(monkeypatch, open_=hatch_open)
            for url in (self.HTTP_URL, self.HTTPS_URL):
                ingest_admits = WebhookURLValidator.validate_webhook_url_registration(url)[0]
                assert ingest_admits == seam_admits(url), (
                    f"ingest and seam disagree on {url} with hatch open={hatch_open}: "
                    f"ingest={ingest_admits}, seam={seam_admits(url)}"
                )


class TestWebhookAuthenticator:
    """Test HMAC-SHA256 webhook authentication."""

    def test_sign_payload(self):
        """Should generate signature with timestamp."""
        payload = {"event": "test", "data": "value"}
        secret = "test_secret_key"

        headers = WebhookAuthenticator.sign_payload(payload, secret)

        assert "X-Webhook-Signature" in headers
        assert "X-Webhook-Timestamp" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")
        assert headers["X-Webhook-Timestamp"].isdigit()

    def test_sign_payload_deterministic(self):
        """Same payload and secret should generate different signatures (due to timestamp)."""
        payload = {"event": "test"}
        secret = "secret"

        headers1 = WebhookAuthenticator.sign_payload(payload, secret)
        time.sleep(1.1)  # Delay to ensure different timestamp (at least 1 second)
        headers2 = WebhookAuthenticator.sign_payload(payload, secret)

        # Timestamps should be different
        assert headers1["X-Webhook-Timestamp"] != headers2["X-Webhook-Timestamp"]
        # Signatures should be different (timestamp is part of signed message)
        assert headers1["X-Webhook-Signature"] != headers2["X-Webhook-Signature"]

    def test_sign_payload_with_different_secrets(self):
        """Different secrets should produce different signatures."""
        payload = {"event": "test"}

        headers1 = WebhookAuthenticator.sign_payload(payload, "secret1")
        headers2 = WebhookAuthenticator.sign_payload(payload, "secret2")

        assert headers1["X-Webhook-Signature"] != headers2["X-Webhook-Signature"]

    def test_verify_signature_valid(self):
        """Should verify valid signature."""
        payload = {"event": "test", "data": "value"}
        secret = "test_secret"

        # Create signature
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload_str}"
        signature = (
            "sha256=" + hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        )

        # Verify
        is_valid = WebhookAuthenticator.verify_signature(payload_str, signature, timestamp, secret)
        assert is_valid

    def test_verify_signature_invalid_secret(self):
        """Should reject signature with wrong secret."""
        payload = {"event": "test"}
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        timestamp = str(int(time.time()))

        # Sign with one secret
        signed_payload = f"{timestamp}.{payload_str}"
        signature = "sha256=" + hmac.new(b"secret1", signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        # Verify with different secret
        is_valid = WebhookAuthenticator.verify_signature(payload_str, signature, timestamp, "secret2")
        assert not is_valid

    def test_verify_signature_replay_protection(self):
        """Should reject old timestamps (replay attack prevention)."""
        payload = {"event": "test"}
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        secret = "test_secret"

        # Create signature with old timestamp (10 minutes ago)
        old_timestamp = str(int(time.time()) - 600)
        signed_payload = f"{old_timestamp}.{payload_str}"
        signature = (
            "sha256=" + hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        )

        # Should reject (default tolerance is 300 seconds / 5 minutes)
        is_valid = WebhookAuthenticator.verify_signature(payload_str, signature, old_timestamp, secret)
        assert not is_valid

    def test_verify_signature_custom_tolerance(self):
        """Should accept old timestamps if tolerance allows."""
        payload = {"event": "test"}
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        secret = "test_secret"

        # Create signature with timestamp 10 minutes ago
        old_timestamp = str(int(time.time()) - 600)
        signed_payload = f"{old_timestamp}.{payload_str}"
        signature = (
            "sha256=" + hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        )

        # Should accept with large tolerance
        is_valid = WebhookAuthenticator.verify_signature(
            payload_str, signature, old_timestamp, secret, tolerance_seconds=3600
        )
        assert is_valid

    def test_roundtrip_sign_and_verify(self):
        """Should successfully sign and verify."""
        payload = {"event": "creative_approved", "creative_id": "cr_123", "status": "active"}
        secret = "super_secret_key_12345"

        # Sign
        headers = WebhookAuthenticator.sign_payload(payload, secret)
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        # Verify
        is_valid = WebhookAuthenticator.verify_signature(
            payload_str, headers["X-Webhook-Signature"], headers["X-Webhook-Timestamp"], secret
        )
        assert is_valid

    def test_signature_without_sha256_prefix(self):
        """Should handle signatures without sha256= prefix."""
        payload = {"event": "test"}
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        secret = "test_secret"
        timestamp = str(int(time.time()))

        # Create signature without prefix
        signed_payload = f"{timestamp}.{payload_str}"
        signature = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        # Should still verify
        is_valid = WebhookAuthenticator.verify_signature(payload_str, signature, timestamp, secret)
        assert is_valid

    def test_tampered_payload(self):
        """Should reject tampered payload."""
        payload = {"event": "test", "amount": 100}
        secret = "test_secret"

        # Sign original payload
        headers = WebhookAuthenticator.sign_payload(payload, secret)

        # Tamper with payload
        tampered_payload = {"event": "test", "amount": 999999}
        tampered_str = json.dumps(tampered_payload, separators=(",", ":"), sort_keys=True)

        # Should reject
        is_valid = WebhookAuthenticator.verify_signature(
            tampered_str, headers["X-Webhook-Signature"], headers["X-Webhook-Timestamp"], secret
        )
        assert not is_valid
