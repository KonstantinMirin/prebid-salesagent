"""Integration tests for the outbound egress seam (`src.core.security.outbound_http`).

Every case drives the real seam against a real local origin. Nothing is mocked:
no patched ``getaddrinfo``, no substituted transport, no faked ``httpx``. The
refusals under test are genuinely produced by the live ``adcp.signing``
validator against real addresses — ``127.0.0.1`` really is in a reserved range
and ``169.254.169.254`` really is a cloud-metadata address — so a mock could
only restate the assertion, never grade it. The same goes for the two facts
that matter most here: "the redirect was not followed" and "the 404 was not
retried" are only provable by counting hits on an origin that actually ran.

Spec grounding: AdCP 3.1.1, ``building/by-layer/L1/security.mdx``, "Webhook URL
validation (SSRF)". A fetcher MUST (1) reject non-HTTPS in production, (2)
reject reserved ranges, (3) pin the connection to the validated IP, (4) refuse
redirects, (5) cap size and timeouts, (6) not echo fetch errors back to the
party that supplied the URL. Conformance storyboard: ungraded — this is an L1
security obligation, not a wire contract.

Every case runs for BOTH ``send`` and ``asend``: the async twin is a separate
code path and an untested one would ship the epic's defect in half the repo.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest

from src.core.exceptions import build_two_layer_error_envelope
from tests.helpers import assert_backoff_schedule, assert_envelope_shape

# Both entry points get every case. Parametrising instead of duplicating the
# module keeps the two paths literally the same test.
SEAM_CALLS = ["send", "asend"]

# A cloud-metadata address: refused unconditionally, escape hatches or not.
METADATA_URL = "https://169.254.169.254/"

# A JSONPath-lite path a CALLER supplies for a refused URL that came out of its
# own request payload. The seam only carries it — the value belongs to the call
# site's namespace (this one is the property-list resolver's), which is why the
# seam cannot derive it and why this file grades the carrying, not the path.
_CALLER_FIELD_PATH = "property_list.agent_url"

# The test-speed knob for the retry backoff base. Written as a literal here for
# the same reason `set_flags` writes the escape-hatch names as literals: the
# tests drive the seam's env surface from outside, not through its privates.
BACKOFF_BASE_ENV = "ADCP_OUTBOUND_BACKOFF_BASE_SECONDS"

# The seam's logger, for grading the fallback warning on a malformed knob value.
SEAM_LOGGER = "src.core.security.outbound_http"


def _seam():
    """Import the seam lazily.

    A module-level import would turn "the seam does not exist yet" into a
    collection error for the whole file, which would also stop the local-origin
    fixture from ever running. Importing per-call keeps each case an
    independent, individually diagnosable failure.
    """
    from src.core.security import outbound_http

    return outbound_http


def call_seam(seam_call: str, url: str, **kwargs: Any):
    """Dispatch to ``send`` or ``asend`` — the one place the two differ."""
    seam = _seam()
    if seam_call == "send":
        return seam.send(url, **kwargs)
    return asyncio.run(seam.asend(url, **kwargs))


def set_flags(monkeypatch, *, private: bool = False, insecure: bool = False) -> None:
    """Set both escape hatches explicitly.

    Always writing both — including the off case, as the literal ``"false"`` the
    repo's ``== "true"`` convention treats as off — pins the test against
    ambient environment rather than assuming the variables are unset.
    """
    monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_PRIVATE", "true" if private else "false")
    monkeypatch.setenv("ADCP_OUTBOUND_ALLOW_INSECURE", "true" if insecure else "false")


def pin_jitter(monkeypatch, value: float) -> list[tuple]:
    """Freeze the seam's jitter draw and record how it was called.

    BR-RULE-029's jitter is a real ``random.uniform(0, 1)`` draw, so any test
    that asserts a delay's magnitude has to pin it — otherwise the assertion is
    graded against a number the test does not know.

    The patch target is the module attribute ``outbound_http.random``, which is
    also the string target the UC-004 circuit-breaker harness patches
    (``tests/harness/delivery_circuit_breaker.py``). Pinning it here for the same
    obligation keeps the seam suite and the BDD suite grading one implementation:
    a ``from random import uniform`` in the seam would break both at once, which
    is the point.

    Returns the list of ``(args)`` tuples the seam passed to ``uniform``, so a
    caller can grade the draw itself — one draw per sleep, with the literal
    ``(0, 1)`` bounds the rule names.
    """
    calls: list[tuple] = []

    def _pinned(*args):
        calls.append(args)
        return value

    monkeypatch.setattr(_seam().random, "uniform", _pinned)
    return calls


def record_sleeps(monkeypatch, seam_call: str) -> list[float]:
    """Capture the durations the seam actually sleeps, without waiting them out.

    Magnitudes of 1s/2s/4s cannot be graded by wall-clock measurement in a test
    suite, so the sleep itself is the observation point. This is the ONLY place
    the two seam paths differ in this file: ``send`` blocks on ``time.sleep`` and
    ``asend`` awaits ``asyncio.sleep``, so a test that patched only one would
    grade half the module.

    The async replacement must be an ``async def`` (or an ``AsyncMock``): a plain
    ``MagicMock`` returns a non-awaitable and the seam would ``TypeError`` on the
    await instead of failing on the schedule.
    """
    seam = _seam()
    durations: list[float] = []

    if seam_call == "send":
        monkeypatch.setattr(seam.time, "sleep", durations.append)
        return durations

    async def _record(seconds: float) -> None:
        durations.append(seconds)

    monkeypatch.setattr(seam.asyncio, "sleep", _record)
    return durations


def fast_backoff(monkeypatch) -> None:
    """Make a retry test's real sleeps negligible without weakening what it grades.

    For the retry tests that grade attempt COUNTS: they have to sleep between
    attempts, but what they sleep is not their obligation — BR-RULE-029's
    magnitudes are graded once, by the schedule section below.

    BOTH halves are required. The base override alone does not make these tests
    fast, because the jitter is an additive ``uniform(0, 1)`` draw independent of
    the base: at a 1ms base each sleep would still average half a second.

    The base is written EXPLICITLY, exactly as ``set_flags`` writes the literal
    ``"false"``, so an ambient value in the shell cannot change what these tests
    wait — the variable is deliberately absent from ``tox.ini``'s ``pass_env``,
    but a bare host ``pytest`` inherits the whole environ.
    """
    monkeypatch.setenv(BACKOFF_BASE_ENV, "0.001")
    pin_jitter(monkeypatch, 0.0)


def assert_blocked(seam_call: str, url: str, **kwargs: Any):
    """Assert the call is refused before any request leaves, and return the error."""
    with pytest.raises(_seam().OutboundRequestBlocked) as excinfo:
        call_seam(seam_call, url, **kwargs)
    return excinfo.value


def assert_delivery_failed(seam_call: str, url: str, **kwargs: Any):
    """Assert the call reached the network but did not deliver, and return the error."""
    with pytest.raises(_seam().OutboundDeliveryFailed) as excinfo:
        call_seam(seam_call, url, **kwargs)
    return excinfo.value


def was_refused_before_connecting(call) -> bool:
    """Whether ``call`` was refused by pre-connection policy, rather than after reaching the wire.

    ``OutboundDeliveryFailed`` and a plain return are both *not* refusals: they
    mean the URL got past scheme and address policy and the outcome was decided
    on the network. Collapsing every outcome to this one boolean is what lets
    the send path and the validate-only path be compared case by case.
    """
    try:
        call()
    except _seam().OutboundRequestBlocked:
        return True
    except _seam().OutboundDeliveryFailed:
        return False
    return False


# ---------------------------------------------------------------------------
# 1. Scheme policy — the one address-adjacent rule the seam owns itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/webhook",
        "ftp://example.com/webhook",
        "file:///etc/passwd",
        "/no/scheme",
    ],
)
def test_non_https_scheme_is_refused_by_default(seam_call, url, monkeypatch):
    """Anything that is not https:// is refused when ADCP_OUTBOUND_ALLOW_INSECURE is off.

    ``example.com`` is a public address, so nothing but the scheme rule can be
    refusing these — that is what makes this a scheme test rather than a
    restatement of the address test below. No DNS lookup happens either: the
    scheme is checked before the transport is built.
    """
    set_flags(monkeypatch)

    error = assert_blocked(seam_call, url)

    assert isinstance(error, _seam().OutboundError)


# ---------------------------------------------------------------------------
# 2. Address policy — delegated to adcp.signing, graded here
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_loopback_over_https_is_refused_without_connecting(seam_call, monkeypatch, local_origin):
    """A reserved-range destination is refused, and the origin is never reached."""
    set_flags(monkeypatch)

    assert_blocked(seam_call, f"https://127.0.0.1:{local_origin.port}/")

    assert local_origin.hits == 0, f"seam connected to a refused address: {local_origin.requests}"


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_cloud_metadata_address_is_refused(seam_call, monkeypatch):
    """The cloud-metadata address is refused under default flags."""
    set_flags(monkeypatch)

    assert_blocked(seam_call, METADATA_URL)


# ---------------------------------------------------------------------------
# 3. Escape hatches, graded one at a time
#
# Under default flags http://127.0.0.1:<port>/ is refused by BOTH the scheme
# rule and the address rule, so a bare `raises` cannot say which one fired and a
# both-flags-on success grades neither alone. One flag at a time fixes that.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_allow_insecure_alone_does_not_open_private_addresses(seam_call, monkeypatch, local_origin):
    """ALLOW_INSECURE relaxes the scheme rule only — the address rule still refuses loopback."""
    set_flags(monkeypatch, insecure=True)

    assert_blocked(seam_call, f"{local_origin.base_url}/webhook")

    assert local_origin.hits == 0


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_allow_private_alone_does_not_open_plain_http(seam_call, monkeypatch, local_origin):
    """ALLOW_PRIVATE relaxes the address rule only — the scheme rule still refuses http://."""
    set_flags(monkeypatch, private=True)

    assert_blocked(seam_call, f"{local_origin.base_url}/webhook")

    assert local_origin.hits == 0


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_both_flags_allow_plain_http_to_the_local_origin(seam_call, monkeypatch, local_origin):
    """With both hatches open the request is delivered, and the result carries the response."""
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.respond_with(200, body=b'{"ok": true}')

    result = call_seam(seam_call, f"{local_origin.base_url}/webhook", json={"hello": "world"})

    assert result.status_code == 200
    assert result.json() == {"ok": True}
    assert result.attempts == 1
    assert result.duration_seconds >= 0
    assert local_origin.hits == 1
    assert local_origin.paths == ["/webhook"]
    # The body has to be streamed so the size cap can be enforced while
    # accumulating, and an exhausted stream makes `.content`/`.text` raise
    # ResponseNotRead. Every migrating call site logs one of those, so the
    # handed-back response must be readable like any other.
    assert result.response.text == '{"ok": true}'
    assert result.response.json() == {"ok": True}


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_cloud_metadata_stays_refused_with_both_flags_on(seam_call, monkeypatch):
    """Metadata blocking is unconditional — no flag combination reaches it."""
    set_flags(monkeypatch, private=True, insecure=True)

    assert_blocked(seam_call, METADATA_URL)


# ---------------------------------------------------------------------------
# 4. Redirects are not followed — the regression that matters most
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_redirect_to_metadata_address_is_not_followed(seam_call, monkeypatch, local_origin):
    """A 302 towards the metadata address is returned, never chased.

    ``requests.Session.request`` defaults ``allow_redirects=True``, so the code
    this seam replaces validated the URL and then followed a 302 to an internal
    address unchecked. The exact hit count is the proof: one hit means the
    seam stopped at the redirect.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.redirect_to(METADATA_URL, status=302)

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=3)

    assert error.last_status == 302
    assert local_origin.hits == 1, f"seam followed the redirect: {local_origin.requests}"


# ---------------------------------------------------------------------------
# 5. Retry classification by status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_server_error_is_retried_to_max_attempts(seam_call, monkeypatch, local_origin):
    """A 5xx is retried up to max_attempts, then reported as a delivery failure."""
    set_flags(monkeypatch, private=True, insecure=True)
    fast_backoff(monkeypatch)
    local_origin.respond_with(503, body=b'{"error": "unavailable"}')

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=3)

    assert error.attempts == 3
    assert error.last_status == 503
    assert local_origin.hits == 3


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_client_error_is_terminal_and_not_retried(seam_call, monkeypatch, local_origin):
    """A 4xx fails on the first attempt — retrying a rejected request only doubles the damage."""
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.respond_with(404, body=b'{"error": "no such hook"}')

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=3)

    assert error.attempts == 1
    assert error.last_status == 404
    assert local_origin.hits == 1


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_max_attempts_one_sends_exactly_once(seam_call, monkeypatch, local_origin):
    """max_attempts counts TOTAL attempts, not retries after the first."""
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.respond_with(503)

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=1)

    assert error.attempts == 1
    assert local_origin.hits == 1


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_retry_recovers_when_the_origin_recovers(seam_call, monkeypatch, local_origin):
    """503, 503, 200 succeeds on the third attempt — a retry that actually recovers.

    Every other retry case here programs a failure that never clears, so all of
    them would still pass if the seam gave up early and reported the failure.
    Only a per-attempt response sequence grades the other half of the contract:
    that attempt N+1 is really sent and its response is really the one returned.
    The origin serves the sequence itself, so the recovery is observed on the
    wire rather than staged by a mock's ``side_effect`` list.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    fast_backoff(monkeypatch)
    local_origin.respond_in_sequence(
        [
            (503, b'{"error": "unavailable"}'),
            (503, b'{"error": "still unavailable"}'),
            (200, b'{"ok": true}'),
        ]
    )

    result = call_seam(seam_call, f"{local_origin.base_url}/webhook", max_attempts=3)

    assert result.status_code == 200
    assert result.json() == {"ok": True}
    assert result.attempts == 3
    assert local_origin.hits == 3


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_response_sequence_repeats_its_last_entry_past_the_end(seam_call, monkeypatch, local_origin):
    """A queue shorter than the attempt count keeps answering with its final entry.

    This pins the origin's own contract, which the recovery case above depends
    on: a test programs the recovery point without having to know how many
    attempts the caller will make. Four attempts against a two-entry queue must
    report the SECOND entry's status, not the first and not a queue-exhausted
    error.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    fast_backoff(monkeypatch)
    local_origin.respond_in_sequence([(429, b'{"error": "slow down"}'), (503, b'{"error": "unavailable"}')])

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=4)

    assert error.attempts == 4
    assert error.last_status == 503
    assert local_origin.hits == 4


# ---------------------------------------------------------------------------
# 6. Retry BACKOFF schedule — BR-RULE-029, graded at the seam
#
# The section above grades HOW MANY times the seam tries. This one grades how
# long it waits between those tries, which is a separate invariant with a
# separate history: production honoured 1s/2s/4s + jitter before the seam
# existed (src/core/webhook_delivery.py), so a seam that waits 0.1s/0.2s/0.4s
# would REGRESS it on both magnitude and randomisation the moment a call site
# migrated across.
#
# The schedule is graded through tests/helpers/backoff_assertions.py, the same
# grader the UC-004 BDD steps and the webhook integration tests use. Encoding
# 1/2/4 a second time here is exactly the drift that grader exists to prevent —
# one copy ends up checking a ratio while the other checks magnitudes, and a
# ratio check passes for 0.1/0.2/0.4.
#
# Both cases run on a plain 503 origin at max_attempts=4: three sleeps, which is
# the only attempt count that reaches the rule's third (4s) step. No
# ``local_origin.delay()`` here — nothing in these tests may reach a real sleep
# through the module a second time.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_backoff_schedule_is_br_rule_029_by_default(seam_call, monkeypatch, local_origin):
    """With no knob set, the seam waits BR-RULE-029's 1s, 2s, 4s — each randomised.

    ``jitter=None`` is the grader's live-jitter mode: every delay must land in
    ``[base, base + 1)`` AND at least one must differ from its base. So this one
    case grades the magnitudes and proves randomisation is actually applied,
    without the test knowing what was drawn.

    The knob is ``delenv``'d rather than assumed absent — the explicit form of
    "unset", matching how ``set_flags`` writes the literal ``"false"``. A bare
    host ``pytest`` inherits the whole environ, and an ambient value here would
    turn a passing default into a silently unrelated assertion.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    monkeypatch.delenv(BACKOFF_BASE_ENV, raising=False)
    local_origin.respond_with(503, body=b'{"error": "unavailable"}')
    durations = record_sleeps(monkeypatch, seam_call)

    assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=4)

    assert_backoff_schedule(durations, jitter=None)


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_backoff_draws_one_uniform_0_1_jitter_per_sleep(seam_call, monkeypatch, local_origin):
    """Each delay is its base PLUS one ``uniform(0, 1)`` draw — additive, once per sleep.

    Pinning the draw turns the window check above into an exact one, so a
    magnitude regression cannot hide inside the jitter slack. The draw itself is
    graded too, and it is the shape of the draw that matters, not just that some
    randomness happened:

    * ``(0, 1)`` as two positional numbers — the same call signature the UC-004
      step asserts (``call.args == (0, 1)``), so the seam and the BDD suite pin
      one implementation rather than two compatible-looking ones.
    * exactly one draw per sleep — which is what putting the draw inside the ONE
      shared ``_backoff_seconds`` helper buys. A draw per attempt, or a copy in
      each of ``send``/``asend``, shows up here as the wrong count.
    * additive, not multiplicative — ``base + pinned``, which is what the UC-004
      step's ``_pinned_jitter`` grading requires of production.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    monkeypatch.delenv(BACKOFF_BASE_ENV, raising=False)
    local_origin.respond_with(503, body=b'{"error": "unavailable"}')
    durations = record_sleeps(monkeypatch, seam_call)
    draws = pin_jitter(monkeypatch, 0.25)

    assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=4)

    assert_backoff_schedule(durations, jitter=0.25)
    assert draws == [(0, 1), (0, 1), (0, 1)], (
        f"expected one uniform(0, 1) draw per backoff sleep, got {draws} for {len(durations)} sleeps"
    )


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_backoff_base_env_knob_moves_the_base_and_nothing_else(seam_call, monkeypatch, local_origin):
    """The knob scales the base; the doubling and the jitter term are untouched.

    This case grades the KNOB, not the rule — the rule is graded two cases above,
    by ``assert_backoff_schedule``. That is why the expected delays are spelled
    out here rather than taken from the grader: the grader encodes 1/2/4, which
    is precisely what an overridden base is not.

    The jitter is pinned as well as the base, because the two are independent: an
    unpinned ``uniform(0, 1)`` dwarfs a 10ms base, and asserting on the sum would
    then be an assertion about the draw, not about the knob.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    monkeypatch.setenv(BACKOFF_BASE_ENV, "0.01")
    local_origin.respond_with(503, body=b'{"error": "unavailable"}')
    durations = record_sleeps(monkeypatch, seam_call)
    pin_jitter(monkeypatch, 0.005)

    assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=4)

    assert durations == pytest.approx([0.015, 0.025, 0.045]), (
        f"expected base 0.01 doubled per attempt plus a pinned 0.005 jitter, got {durations}"
    )


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
@pytest.mark.parametrize("bad_value", ["abc", "-1", "0"])
def test_unusable_backoff_base_falls_back_to_the_rule_and_warns(
    seam_call, bad_value, monkeypatch, local_origin, caplog
):
    """A knob value that is not a strictly positive number is ignored, loudly.

    The failure mode this closes is silent disarmament: the knob exists only for
    test speed, so a value the seam cannot use must never quietly become "no
    backoff" or "some other backoff" — it falls back to BR-RULE-029 and says so.

    Zero is rejected with the malformed values on purpose. Read literally it asks
    for "jitter only, no base delay", and honouring that would delete the
    invariant this ticket restores; falling back silently would instead hand the
    caller a 1s base it did not ask for. Refusing it out loud is the only reading
    that surprises nobody.

    The warning must name the variable — an operator who cannot see which knob
    was ignored cannot fix it.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    monkeypatch.setenv(BACKOFF_BASE_ENV, bad_value)
    local_origin.respond_with(503, body=b'{"error": "unavailable"}')
    durations = record_sleeps(monkeypatch, seam_call)
    pin_jitter(monkeypatch, 0.25)

    with caplog.at_level(logging.WARNING, logger=SEAM_LOGGER):
        assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=4)

    assert_backoff_schedule(durations, jitter=0.25)

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == SEAM_LOGGER and record.levelno >= logging.WARNING and BACKOFF_BASE_ENV in record.getMessage()
    ]
    assert warnings, (
        f"{bad_value!r} was ignored silently: no WARNING from {SEAM_LOGGER} naming {BACKOFF_BASE_ENV}. "
        f"Records seen: {[(r.name, r.levelname, r.getMessage()) for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# 7. Retry classification by exception — httpx signals these as exceptions,
#    never as a status, and they must not escape the seam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_timeout_is_retried_and_surfaces_as_delivery_failure(seam_call, monkeypatch, local_origin):
    """A stalled origin trips the per-request timeout, is retried, then fails typed.

    ``last_status`` is None because there was never a response to read a status
    from. If this leaked a raw ``httpx.ReadTimeout`` instead, every migrated
    call site would have to keep its own ``except httpx...`` — which is the
    duplication the seam exists to delete.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    fast_backoff(monkeypatch)
    local_origin.delay(2.0)

    error = assert_delivery_failed(
        seam_call,
        f"{local_origin.base_url}/webhook",
        timeout=0.5,
        max_attempts=2,
    )

    assert error.attempts == 2
    assert error.last_status is None
    assert local_origin.hits == 2


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_origin_closing_without_responding_is_retried_then_fails_typed(seam_call, monkeypatch, local_origin):
    """An origin that hangs up mid-exchange is a retryable transport failure, not a leak.

    The origin accepts the request, records the hit, and closes the socket
    before writing a status line, so httpx raises ``RemoteProtocolError``
    ("Server disconnected without sending a response") of its own accord. That
    is the distinction from the timeout case above: a different httpx exception
    class reaching the same classification, from a real protocol violation on
    the wire rather than a stalled read.

    ``last_status`` is None for the same reason as a timeout — there was never a
    response to read a status from — and the raw httpx error must not escape,
    or every migrated call site keeps its own ``except httpx...``.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    fast_backoff(monkeypatch)
    local_origin.close_without_responding()

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=2)

    assert error.attempts == 2
    assert error.last_status is None
    assert local_origin.hits == 2


# ---------------------------------------------------------------------------
# 8. Response-size cap — spec point 5's other half
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_oversized_response_body_is_refused_and_not_retried(seam_call, monkeypatch, local_origin):
    """A chunked body past the cap aborts the read; retrying it would only re-read it.

    httpx applies no default body limit, so an unbounded counterparty response
    is a memory-exhaustion vector. The body is chunked, not Content-Length'd,
    so the cap has to be enforced while accumulating rather than by reading a
    declared length.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    cap = _seam()._MAX_RESPONSE_BYTES
    local_origin.respond_chunked(cap + 1, chunk_size=64 * 1024)

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=3)

    assert error.attempts == 1
    assert local_origin.hits == 1


# ---------------------------------------------------------------------------
# 9. Error opacity, asserted on the wire envelope (spec point 6)
#
# The repo's error-verification policy makes the envelope the authority, not
# `.message` — `details` rides to the buyer too, via
# build_two_layer_error_envelope -> adcp_error(details=...).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_blocked_envelope_hides_the_resolved_address_and_the_reason(seam_call, monkeypatch):
    """A refused address yields one indistinguishable envelope, whatever the real cause.

    The SDK's own messages say "resolved IP <IP> is in a reserved range" versus
    "cannot resolve host '<host>'". Echoing either back tells whoever supplied
    the URL both the resolved address and whether the name exists — an internal
    port and host scanner. The two envelopes must be identical.
    """
    set_flags(monkeypatch)

    reserved = assert_blocked(seam_call, "https://127.0.0.1/webhook")
    unresolvable = assert_blocked(seam_call, "https://no-such-host.invalid/webhook")

    reserved_envelope = build_two_layer_error_envelope(reserved)
    unresolvable_envelope = build_two_layer_error_envelope(unresolvable)

    assert_envelope_shape(reserved_envelope, "INVALID_REQUEST", recovery="correctable")
    assert_envelope_shape(unresolvable_envelope, "INVALID_REQUEST", recovery="correctable")

    reserved_message = reserved_envelope["errors"][0]["message"]
    unresolvable_message = unresolvable_envelope["errors"][0]["message"]
    assert reserved_message == unresolvable_message, (
        "blocked-message distinguishes an unresolvable host from a reserved address: "
        f"{unresolvable_message!r} vs {reserved_message!r}"
    )

    for envelope, forbidden in (
        (reserved_envelope, "127.0.0.1"),
        (unresolvable_envelope, "no-such-host.invalid"),
    ):
        assert forbidden not in json.dumps(envelope), f"{forbidden!r} leaked into {envelope}"

    for term in ("reserved", "resolve", "metadata", "private"):
        assert term not in reserved_message.lower(), f"refusal reason {term!r} leaked into {reserved_message!r}"


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_carried_field_does_not_discriminate_the_refusal_cause(seam_call, monkeypatch):
    """A carried ``field`` names the caller's input on both layers — and nothing else.

    ``field`` is a PASSTHROUGH: the seam sees a URL string, not a request
    document, so it cannot compute a JSONPath-lite path and does not try. It
    carries the one the caller supplies, because the caller is the only party
    that knows whether the refused URL came off the wire and under which name
    (``core/error.json`` @3.1.1: ``field`` is a path into the REQUEST PAYLOAD).

    The grading is EQUALITY of the two whole envelopes, not a per-cause field
    assertion, and that is the point of putting this beside
    ``test_blocked_envelope_hides_the_resolved_address_and_the_reason``: once
    ``field`` rides the refusal it becomes a candidate scheme-vs-address
    discriminator, exactly the spec point 6 side channel that test exists to
    close. Two per-cause assertions would both pass while the two envelopes
    disagreed. Whole-envelope equality is also strictly stronger than the
    neighbour's ``errors[0]["message"]`` comparison — it covers ``details``,
    ``suggestion``, ``recovery`` and ``field`` on both layers at once.

    The second half pins the default: a caller that supplies no ``field`` gets
    no ``field`` KEY, not a null. Every one of the 15 unmigrated
    ``# FIXME(#1589)`` call sites and both existing callers fetch stored
    operator config, where there is no request-payload path to name; emitting
    one would invent a path the buyer never sent, which Level 2 makes worse
    than silence (``error-handling.mdx:16`` — ``field`` exists so an agent can
    SELF-CORRECT, and it cannot correct a path absent from its own document).
    """
    set_flags(monkeypatch)

    reserved = assert_blocked(seam_call, "https://127.0.0.1/webhook", field=_CALLER_FIELD_PATH)
    unresolvable = assert_blocked(seam_call, "https://no-such-host.invalid/webhook", field=_CALLER_FIELD_PATH)

    reserved_envelope = build_two_layer_error_envelope(reserved)
    unresolvable_envelope = build_two_layer_error_envelope(unresolvable)

    assert_envelope_shape(reserved_envelope, "INVALID_REQUEST", recovery="correctable", field=_CALLER_FIELD_PATH)
    assert reserved_envelope == unresolvable_envelope, (
        "the refusal envelope distinguishes an unresolvable host from a reserved address: "
        f"{unresolvable_envelope} vs {reserved_envelope}"
    )

    for envelope, forbidden in (
        (reserved_envelope, "127.0.0.1"),
        (unresolvable_envelope, "no-such-host.invalid"),
    ):
        assert forbidden not in json.dumps(envelope), f"{forbidden!r} leaked into {envelope}"

    fieldless = build_two_layer_error_envelope(assert_blocked(seam_call, "https://127.0.0.1/webhook"))

    assert "field" not in fieldless["adcp_error"], f"adcp_error carries a field key with no caller field: {fieldless}"
    assert "field" not in fieldless["errors"][0], f"errors[0] carries a field key with no caller field: {fieldless}"


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
@pytest.mark.parametrize(
    ("label", "field"),
    [
        ("the url itself", "https://127.0.0.1/webhook"),
        ("a url with other text", "agent_url=https://127.0.0.1/webhook"),
        ("a bare scheme", "ftp://"),
    ],
)
def test_a_field_carrying_a_url_is_refused_outright(seam_call, label, field, monkeypatch):
    """The seam refuses to carry a ``field`` that would leak the destination.

    ``field`` reaches the buyer, and the refusal message deliberately says
    nothing about the cause (spec point 6). A call site that passed the URL as
    the field would route straight around that silence, in a value the message
    never touches — so the rule cannot be documentation only.

    It raises rather than dropping the value: naming a URL where a request path
    belongs is a call-site bug, and swallowing it would ship that bug as a
    quietly fieldless envelope nobody notices.
    """
    set_flags(monkeypatch)

    with pytest.raises(ValueError, match="not a URL"):
        call_seam(seam_call, "https://127.0.0.1/webhook", field=field)


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_a_jsonpath_lite_field_is_carried(seam_call, monkeypatch):
    """The legitimate form is not caught by the URL check — the guard has to let real paths through."""
    set_flags(monkeypatch)

    error = assert_blocked(seam_call, "https://127.0.0.1/webhook", field=_CALLER_FIELD_PATH)

    assert_envelope_shape(
        build_two_layer_error_envelope(error),
        "INVALID_REQUEST",
        recovery="correctable",
        field=_CALLER_FIELD_PATH,
    )


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_delivery_failure_envelope_hides_the_origin_response(seam_call, monkeypatch, local_origin):
    """A failed fetch reports attempts and status — never the origin's body or address."""
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.respond_with(503, body=b'{"detail": "LEAKED-ORIGIN-BODY-MARKER"}')

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=2)
    envelope = build_two_layer_error_envelope(error)

    assert_envelope_shape(envelope, "SERVICE_UNAVAILABLE", recovery="transient")
    assert envelope["errors"][0]["details"] == {"attempts": 2, "last_status": 503}

    serialized = json.dumps(envelope)
    assert "LEAKED-ORIGIN-BODY-MARKER" not in serialized
    assert local_origin.host not in serialized
    assert str(local_origin.port) not in serialized


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_transport_failure_envelope_hides_the_httpx_error(seam_call, monkeypatch, local_origin):
    """A timeout reports last_status=None — never the httpx error string, which names the address."""
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.delay(2.0)

    error = assert_delivery_failed(
        seam_call,
        f"{local_origin.base_url}/webhook",
        timeout=0.5,
        max_attempts=1,
    )
    envelope = build_two_layer_error_envelope(error)

    assert_envelope_shape(envelope, "SERVICE_UNAVAILABLE", recovery="transient")
    assert envelope["errors"][0]["details"] == {"attempts": 1, "last_status": None}

    serialized = json.dumps(envelope)
    assert local_origin.host not in serialized
    assert str(local_origin.port) not in serialized
    for term in ("timeout", "timed out", "readtimeout", "connecterror"):
        assert term not in serialized.lower(), f"httpx internals {term!r} leaked into {envelope}"


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
def test_disconnect_envelope_is_indistinguishable_from_a_timeout_envelope(seam_call, monkeypatch, local_origin):
    """A hang-up and a timeout produce the same envelope — which failure mode it was stays inside.

    Both are ``last_status: None`` after the same attempt count. Telling the two
    apart would tell whoever supplied the URL whether the destination accepted
    the connection and then hung up, or never answered at all — a liveness probe
    for internal hosts (spec point 6). httpx's own wording for this one is
    "Server disconnected without sending a response", which names the failure
    mode outright and must not reach the wire.
    """
    set_flags(monkeypatch, private=True, insecure=True)
    local_origin.close_without_responding()

    error = assert_delivery_failed(seam_call, f"{local_origin.base_url}/webhook", max_attempts=1)
    envelope = build_two_layer_error_envelope(error)

    assert_envelope_shape(envelope, "SERVICE_UNAVAILABLE", recovery="transient")
    assert envelope["errors"][0]["details"] == {"attempts": 1, "last_status": None}

    serialized = json.dumps(envelope)
    assert local_origin.host not in serialized
    assert str(local_origin.port) not in serialized
    for term in ("disconnect", "remoteprotocolerror", "protocol", "without sending"):
        assert term not in serialized.lower(), f"httpx internals {term!r} leaked into {envelope}"


# ---------------------------------------------------------------------------
# 10. validate_url — the same policy, for URLs that are STORED rather than sent
#
# A webhook URL accepted at ingest is persisted now and fetched later, possibly
# by a background worker, so the refusal a buyer can act on has to be issued at
# ingest — before there is a request to attach it to. The obligation is not
# "validate_url refuses bad URLs" (a second hand-written copy of address policy
# would also do that, and that copy is the recurrence this seam exists to make
# impossible). It is that validate_url's verdict is IDENTICAL to send's, case
# for case, and that it reaches nothing while producing it.
# ---------------------------------------------------------------------------

# Every pre-connection decision the seam makes, as (url factory, escape hatches).
# The factory takes the live local origin so a case can target a real address.
# Nothing here leaves the machine: every case is refused, loopback, or both.
PRE_CONNECTION_CASES = {
    "plain-http-public": (lambda origin: "http://example.com/webhook", {}),
    "ftp-scheme": (lambda origin: "ftp://example.com/webhook", {}),
    "file-scheme": (lambda origin: "file:///etc/passwd", {}),
    "no-scheme": (lambda origin: "/no/scheme", {}),
    "https-unresolvable-host": (lambda origin: "https://no-such-host.invalid/webhook", {}),
    "https-loopback": (lambda origin: f"https://127.0.0.1:{origin.port}/", {}),
    "cloud-metadata": (lambda origin: METADATA_URL, {}),
    "cloud-metadata-both-hatches": (lambda origin: METADATA_URL, {"private": True, "insecure": True}),
    "http-loopback-insecure-hatch-only": (lambda origin: f"{origin.base_url}/webhook", {"insecure": True}),
    "http-loopback-private-hatch-only": (lambda origin: f"{origin.base_url}/webhook", {"private": True}),
    "http-loopback-both-hatches": (
        lambda origin: f"{origin.base_url}/webhook",
        {"private": True, "insecure": True},
    ),
}


@pytest.mark.parametrize("seam_call", SEAM_CALLS)
@pytest.mark.parametrize("case_id", sorted(PRE_CONNECTION_CASES))
def test_validate_url_reaches_the_same_verdict_as_the_send_path(seam_call, case_id, monkeypatch, local_origin):
    """For every pre-connection case, validate_url refuses iff the send path refuses.

    Asserting the two verdicts AGAINST EACH OTHER rather than against a
    hardcoded expectation is the point: a re-implementation that happened to
    agree on the cases someone thought to list would pass a hardcoded test and
    diverge on the next one. This can only pass while both paths make the
    decision in the same place — the escape hatches included, since a validator
    that read the flags differently would surface here as a disagreement rather
    than as a silent ingest-time refusal of URLs the fetcher would accept.

    The accepted case is graded too: a validator that refused everything would
    satisfy "refuses what send refuses" and quietly break every ingest path.
    """
    make_url, flags = PRE_CONNECTION_CASES[case_id]
    url = make_url(local_origin)

    # Validate first, on a still-untouched origin, so hits made by the send call
    # below can never be mistaken for hits made by the validator.
    set_flags(monkeypatch, **flags)
    validate_refused = was_refused_before_connecting(lambda: _seam().validate_url(url))

    assert local_origin.hits == 0, f"validate_url opened a connection: {local_origin.requests}"

    set_flags(monkeypatch, **flags)
    send_refused = was_refused_before_connecting(lambda: call_seam(seam_call, url, max_attempts=1))

    assert validate_refused == send_refused, (
        f"validate_url and {seam_call} disagree on {case_id} ({url!r}): "
        f"validate_url {'refused' if validate_refused else 'accepted'}, "
        f"{seam_call} {'refused' if send_refused else 'accepted'}"
    )


def test_validate_url_accepts_a_reachable_destination_without_reaching_it(monkeypatch, local_origin):
    """An acceptable URL passes validation, returns nothing, and the origin never hears about it.

    Returning None rather than the resolved address is deliberate. Handing a
    call site an IP invites it to store or log the resolution and to connect by
    it later, and a resolution reused across the ingest/fetch gap is exactly the
    DNS-rebinding window the SDK's resolve-once-then-pin closes *within* one
    request. The later fetch has to resolve again through its own send call.
    """
    set_flags(monkeypatch, private=True, insecure=True)

    assert _seam().validate_url(f"{local_origin.base_url}/webhook") is None

    assert local_origin.hits == 0, f"validate_url opened a connection: {local_origin.requests}"


def test_validate_url_refusal_envelope_hides_the_resolved_address_and_the_reason(monkeypatch):
    """Ingest-time refusals are as opaque as send-time ones — same message, same envelope.

    An ingest-time validator is the easier place to leak, because its whole job
    is to explain to the caller why the URL is unacceptable. Spec point 6 does
    not relax there: distinguishing "reserved range" from "does not resolve"
    turns URL submission into an internal host and port scanner.
    """
    set_flags(monkeypatch)
    seam = _seam()

    with pytest.raises(seam.OutboundRequestBlocked) as reserved_info:
        seam.validate_url("https://127.0.0.1/webhook")
    with pytest.raises(seam.OutboundRequestBlocked) as unresolvable_info:
        seam.validate_url("https://no-such-host.invalid/webhook")

    reserved_envelope = build_two_layer_error_envelope(reserved_info.value)
    unresolvable_envelope = build_two_layer_error_envelope(unresolvable_info.value)

    assert_envelope_shape(reserved_envelope, "INVALID_REQUEST", recovery="correctable")
    assert_envelope_shape(unresolvable_envelope, "INVALID_REQUEST", recovery="correctable")

    reserved_message = reserved_envelope["errors"][0]["message"]
    assert reserved_message == unresolvable_envelope["errors"][0]["message"]

    for envelope, forbidden in (
        (reserved_envelope, "127.0.0.1"),
        (unresolvable_envelope, "no-such-host.invalid"),
    ):
        assert forbidden not in json.dumps(envelope), f"{forbidden!r} leaked into {envelope}"

    for term in ("reserved", "resolve", "metadata", "private"):
        assert term not in reserved_message.lower(), f"refusal reason {term!r} leaked into {reserved_message!r}"
