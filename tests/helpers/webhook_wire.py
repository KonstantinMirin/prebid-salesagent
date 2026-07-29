"""One capture point for outbound webhook bytes, and the two wire oracles (#1291 C1).

Every AdCP webhook sender in ``src/`` is graded the same way: run the REAL
production sender, replace only the SOCKET, and assert on the bytes and headers
that would have gone out. That needs one capture that spans the three HTTP
clients the senders use today and the one the SDK uses after C1
(``salesagent-z6nr.18``) routes them all through
:class:`adcp.webhooks.WebhookSender`:

===========================================  ==========================================
sender                                       client
===========================================  ==========================================
``protocol_webhook_service.py:296``          ``requests.Session.post``
``webhook_delivery_service.py:484``          ``httpx.Client.post``
``order_approval_service.py:403``            ``httpx.Client.post``
``notification_proof_service.py:91``         ``httpx.AsyncClient.post``
``mock_ad_server.py:512``                    ``requests.post``
``adcp.webhooks.WebhookSender._send_bytes``  ``httpx.AsyncClient.post`` over a pinned
                                             IP transport
===========================================  ==========================================

Spanning all of them is what keeps a red test red for the RIGHT reason: a capture
that only knew ``httpx`` would report "no webhook was sent" for a sender that is
merely still on ``requests``, hiding the assertion the test exists to make.

Only the network is replaced. httpx and requests still perform their own header
building and body encoding, so :attr:`CapturedWebhook.content` is byte-for-byte
what the socket would have carried — which is the whole point, since the defect
class under test (#1441) is precisely "the bytes signed are not the bytes sent".

``build_async_ip_pinned_transport`` is stubbed alongside the clients because it
resolves the destination through real DNS before the SDK signs anything. DNS is a
true external; leaving it live would make every test depend on whether the box can
resolve ``buyer.example.com`` (it cannot), and the resulting ``SSRFValidationError``
would masquerade as a signing failure.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import requests

#: What a captured delivery answers with. Success, so a sender's retry loop stops
#: after one attempt and the capture holds exactly the deliveries the code chose
#: to make rather than a burst of retries.
_ACCEPTED_BODY = b'{"status":"received"}'


@dataclass(frozen=True)
class CapturedWebhook:
    """One outbound POST, as the receiving socket would have seen it."""

    url: str
    headers: httpx.Headers
    content: bytes

    @property
    def payload(self) -> dict[str, Any]:
        """The body parsed as JSON. Raises if the sender sent something else."""
        return json.loads(self.content)


def _record(captured: list[CapturedWebhook], url: str, headers: Any, body: Any) -> None:
    if body is None:
        body = b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    captured.append(CapturedWebhook(url=str(url), headers=httpx.Headers(headers), content=bytes(body)))


def _requests_response(status_code: int) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = _ACCEPTED_BODY
    response.headers["Content-Type"] = "application/json"
    return response


@contextmanager
def stub_outbound_webhooks(responder: Callable[..., Any]) -> Iterator[None]:
    """Replace the SOCKET under every outbound webhook client with *responder*.

    ``responder(url, headers=<dict>, content=<bytes>)`` is called once per POST
    and returns anything carrying a ``status_code`` — or raises, which is how the
    timeout / connection-error ladders are driven. It is deliberately callable
    rather than a fixed answer so a ``unittest.mock.MagicMock`` can BE the
    responder: the harness gets ``call_args`` / ``call_count`` / ``side_effect``
    on real wire bytes, and the signing suites get :func:`capture_outbound_webhooks`
    — one stub, two shapes, instead of two stubs that drift.
    """
    real_client = httpx.Client
    real_async_client = httpx.AsyncClient

    def _handler(request: httpx.Request) -> httpx.Response:
        request.read()
        answer = responder(str(request.url), headers=httpx.Headers(request.headers), content=request.content)
        return httpx.Response(
            int(answer.status_code), content=_ACCEPTED_BODY, headers={"Content-Type": "application/json"}
        )

    transport = httpx.MockTransport(_handler)

    def _sync_client(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    def _async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    def _session_post(_self: requests.Session, url: str, **kwargs: Any) -> requests.Response:
        return _requests_post(url, **kwargs)

    def _requests_post(url: str, **kwargs: Any) -> requests.Response:
        # Prepared through requests' own machinery, so the recorded bytes are the
        # ones requests would have written — including its ``{"a": 1}`` spacing,
        # which is the divergence #1441 is about.
        prepared = requests.Request(
            method="POST",
            url=url,
            headers=kwargs.get("headers"),
            json=kwargs.get("json"),
            data=kwargs.get("data"),
        ).prepare()
        answer = responder(str(prepared.url), headers=httpx.Headers(prepared.headers), content=prepared.body or b"")
        return _requests_response(int(answer.status_code))

    with ExitStack() as stack:
        stack.enter_context(patch("httpx.Client", _sync_client))
        stack.enter_context(patch("httpx.AsyncClient", _async_client))
        # Patched at BOTH the definition module and the SDK sender module that
        # imports the name at import time — patching only one leaves a live DNS
        # lookup on whichever path the code under test happens to take.
        for target in (
            "adcp.signing.ip_pinned_transport.build_async_ip_pinned_transport",
            "adcp.webhook_sender.build_async_ip_pinned_transport",
        ):
            stack.enter_context(patch(target, lambda *a, **k: transport))
        stack.enter_context(patch.object(requests.Session, "post", _session_post))
        stack.enter_context(patch("requests.post", _requests_post))
        yield


@contextmanager
def capture_outbound_webhooks(status_codes: Sequence[int] = ()) -> Iterator[list[CapturedWebhook]]:
    """Record every outbound POST made through httpx or requests inside the block.

    The list is appended to in call order, so ``len(captured)`` grades "was the
    receiver told at all" — a leg that must be asserted before any header
    assertion, because "no webhook" and "an unsigned webhook" are different
    defects.

    ``status_codes`` answers the Nth delivery with the Nth code, holding the last
    one thereafter; the default answers every delivery ``200``. It exists so a
    sender's retry ladder can be driven through the same capture that grades its
    bytes.
    """
    captured: list[CapturedWebhook] = []

    def _responder(url: str, *, headers: Any, content: Any) -> SimpleNamespace:
        _record(captured, url, headers, content)
        status = 200 if not status_codes else status_codes[min(len(captured) - 1, len(status_codes) - 1)]
        return SimpleNamespace(status_code=status)

    with stub_outbound_webhooks(_responder):
        yield captured


def signature_input_params(captured: CapturedWebhook, label: str = "sig1") -> dict[str, str | int]:
    """The RFC 9421 ``Signature-Input`` parameters, parsed by the SDK's own parser.

    Parsing rather than substring-matching is what makes the ``tag=`` assertion
    real: ``tag`` is a structured-field parameter, and a hand-rolled ``in`` check
    would also pass for a tag that merely CONTAINS the profile string.
    """
    from adcp.signing.canonical import parse_signature_input_header

    header = captured.headers.get("signature-input")
    assert header, (
        "no Signature-Input header on the outbound webhook — the receiver has nothing to verify; "
        f"headers were {sorted(captured.headers.keys())}"
    )
    parsed = parse_signature_input_header(header)
    assert label in parsed, f"Signature-Input carries labels {sorted(parsed)}, not {label!r}"
    return parsed[label].params
