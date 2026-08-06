"""Contract: the capture service records the WIRE, not just the parsed payload.

``tests/e2e/webhook_capture_service.py`` does not exist yet — this is the TDD red
step for salesagent-mp53.9's port of the long-lived webhook-capture compose
service. It runs the service IN-PROCESS on loopback (no Docker, no compose
network, no tls-proxy), because the claims below are about this module's own
request handling, not about the stack wiring (that is
``tests/unit/test_architecture_e2e_webhook_capture_wiring.py`` and
``tests/e2e/test_webhook_capture_egress_gate_e2e.py``).

**Why this module exists at all, given the sibling branch already has a service.**
The version being ported (``feat/secure-outbound-fetch``) parses each request
body with ``json.loads`` and stores the resulting dict — it DISCARDS the request
headers and the exact bytes. That is fine on that branch and fatal on this one:
this branch's in-process receiver records ``received_raw`` as
``(path, headers, body_bytes)`` (``tests/e2e/_webhook_capture.py``, #1291 C1),
and ``tests/e2e/test_webhook_signature_e2e.py`` grades RFC 9421 signatures out of
it. A signature is computed over the BYTES the sender emitted and over the
``Signature`` / ``Signature-Input`` / ``Content-Digest`` headers; a service that
returns a re-serialized dict has thrown away the entire subject of that test,
and it would do so SILENTLY — the payload assertions would keep passing while
signature verification failed as ``webhook_signature_invalid``, the failure mode
most likely to be misread as a crypto bug.

**The contract this pins**, chosen to be additive so the ported consumers keep
working unchanged: ``GET``/``DELETE /webhook/<key>`` answer with BOTH

* ``received``     — the parsed JSON payloads, exactly as the sibling branch's
  service already returns them; and
* ``received_raw`` — one entry per request, ``{"path", "headers", "body_b64"}``,
  reconstituting this branch's ``(path, headers, body_bytes)`` tuple across an
  HTTP readback hop (base64 because the bytes are not necessarily text, let
  alone JSON).
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from http.client import HTTPException, HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

# This import is the TDD red: tests/e2e/webhook_capture_service.py does not exist
# yet — it is created by the implementation atom.
from tests.e2e.webhook_capture_service import run_capture_service

_TIMEOUT_SECONDS = 5.0

#: A realistic RFC 9421 header set. The values are opaque to the service — that
#: is the point: it must hand back what it was given, byte for byte, with no
#: normalization of its own.
_SIGNATURE_HEADERS = {
    "Signature": "sig1=:dGVzdC1zaWduYXR1cmUtYnl0ZXM=:",
    "Signature-Input": 'sig1=("@method" "@target-uri" "content-digest");created=1754400000;keyid="k1";alg="ed25519";tag="adcp-webhook-v1"',
    "Content-Digest": "sha-256=:X48E9qOokqqrvdts8nOJRJN3OWDUoyWxBf7kbu9DBPE=:",
}

#: Valid JSON whose exact byte sequence differs from any canonical
#: re-serialization: irregular spacing, a trailing newline, and a non-ASCII
#: character. A service that parses and re-encodes cannot reproduce this.
_UNCANONICAL_BODY = b'{"event":"delivery_report",  "media_buy_id" : "mb_1",\n "note": "caf\xc3\xa9"}\n'


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    """Issue one request against the running service; return ``(status, decoded_json)``.

    A dropped connection is reported as status ``0`` rather than raised, so an
    unhandled exception inside the service reads as a failed assertion about the
    contract instead of an opaque transport error in the test.
    """
    req = Request(f"{base_url}{path}", data=body, method=method)
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    try:
        resp: HTTPResponse = urlopen(req, timeout=_TIMEOUT_SECONDS)  # noqa: S310 - test-only, loopback origin
        status, raw = resp.status, resp.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (URLError, HTTPException):
        return 0, {}
    return status, (json.loads(raw) if raw else {})


def _post(base_url: str, key: str, body: bytes, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    return _request(base_url, "POST", f"/webhook/{key}", body=body, headers=headers)


def _get(base_url: str, key: str) -> tuple[int, dict]:
    return _request(base_url, "GET", f"/webhook/{key}")


def _delete(base_url: str, key: str) -> tuple[int, dict]:
    return _request(base_url, "DELETE", f"/webhook/{key}")


def _header(entry: dict, name: str) -> str | None:
    """Case-insensitive header lookup, the way every HTTP client treats header names."""
    lowered = name.lower()
    for key, value in entry["headers"].items():
        if key.lower() == lowered:
            return value
    return None


def _body_bytes(entry: dict) -> bytes:
    return base64.b64decode(entry["body_b64"])


@pytest.fixture
def capture_service(monkeypatch) -> Iterator[str]:
    """Run the capture service on an ephemeral loopback port for one test."""
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "mp539-raw-capture-test")
    with run_capture_service(host="127.0.0.1", port=0) as base_url:
        yield base_url


class TestRawBytesSurviveTheCaptureHop:
    """The exact bytes the sender emitted are readable back, unmodified.

    RFC 9421's ``content-digest`` covers the body bytes, so anything that
    re-serializes the payload changes the digest and every signature over it.
    """

    def test_readback_returns_the_posted_bytes_verbatim(self, capture_service):
        key = uuid.uuid4().hex

        post_status, _ = _post(capture_service, key, _UNCANONICAL_BODY, _SIGNATURE_HEADERS)
        get_status, body = _get(capture_service, key)

        assert post_status == 200
        assert get_status == 200
        assert [_body_bytes(entry) for entry in body["received_raw"]] == [_UNCANONICAL_BODY]

    def test_the_parsed_payload_is_returned_alongside_the_raw_bytes(self, capture_service):
        """``received`` keeps its existing shape — raw capture is additive, not a replacement."""
        key = uuid.uuid4().hex

        _post(capture_service, key, _UNCANONICAL_BODY, _SIGNATURE_HEADERS)
        _, body = _get(capture_service, key)

        assert body["received"] == [json.loads(_UNCANONICAL_BODY)]

    def test_a_body_that_is_not_json_is_still_captured_raw(self, capture_service):
        """Raw capture happens BEFORE parsing, so an unparseable body still explains itself.

        The in-process receiver this replaces states the ordering explicitly:
        ``record_raw`` "runs BEFORE :meth:`record`, so a handler whose ``record``
        rejects a payload still leaves the raw request available to explain why".
        Losing that turns a malformed-payload delivery into "no webhook arrived".
        """
        key = uuid.uuid4().hex
        garbage = b"\x00\x01 not json at all \xff"

        post_status, _ = _post(capture_service, key, garbage, {"Content-Type": "application/octet-stream"})
        get_status, body = _get(capture_service, key)

        assert post_status >= 400, "an unparseable body must be answered with an error, never a quiet 200"
        assert get_status == 200
        assert [_body_bytes(entry) for entry in body["received_raw"]] == [garbage]


class TestSigningHeadersSurviveTheCaptureHop:
    """The RFC 9421 headers arrive intact — they are half of what a signature covers."""

    @pytest.mark.parametrize("header_name", sorted(_SIGNATURE_HEADERS))
    def test_each_signing_header_is_returned_with_its_exact_value(self, capture_service, header_name):
        key = uuid.uuid4().hex

        _post(capture_service, key, _UNCANONICAL_BODY, _SIGNATURE_HEADERS)
        _, body = _get(capture_service, key)

        entry = body["received_raw"][0]
        assert _header(entry, header_name) == _SIGNATURE_HEADERS[header_name]

    def test_the_request_path_is_recorded(self, capture_service):
        """``@target-uri`` / ``@path`` are covered components; the receiver must know what was dialled."""
        key = uuid.uuid4().hex

        _post(capture_service, key, _UNCANONICAL_BODY, _SIGNATURE_HEADERS)
        _, body = _get(capture_service, key)

        assert body["received_raw"][0]["path"] == f"/webhook/{key}"


class TestRawCapturesAreKeyedAndDrainedLikePayloads:
    """Raw capture inherits the isolation and drain semantics the payload list already has."""

    def test_two_keys_never_see_each_others_raw_captures(self, capture_service):
        key_a, key_b = uuid.uuid4().hex, uuid.uuid4().hex

        _post(capture_service, key_a, b'{"for":"a"}', _SIGNATURE_HEADERS)
        _post(capture_service, key_b, b'{"for":"b"}', _SIGNATURE_HEADERS)

        _, body_a = _get(capture_service, key_a)
        _, body_b = _get(capture_service, key_b)

        assert [_body_bytes(e) for e in body_a["received_raw"]] == [b'{"for":"a"}']
        assert [_body_bytes(e) for e in body_b["received_raw"]] == [b'{"for":"b"}']

    def test_delete_drains_the_raw_captures_too(self, capture_service):
        """A drained key must not leave raw entries behind for the next test to trip over."""
        key = uuid.uuid4().hex
        _post(capture_service, key, _UNCANONICAL_BODY, _SIGNATURE_HEADERS)

        delete_status, drained = _delete(capture_service, key)
        _, after = _get(capture_service, key)

        assert delete_status == 200
        assert [_body_bytes(e) for e in drained["received_raw"]] == [_UNCANONICAL_BODY]
        assert after["received_raw"] == []
