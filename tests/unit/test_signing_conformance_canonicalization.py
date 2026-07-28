"""L1(b) — the 31 URL-canonicalization cases, through OUR seam.

#1291 B3 (``salesagent-z6nr.14``), design step 4. ``chopmob-cloud`` noted on #1291
that cross-implementation signing-base parity is where RFC 9421 implementations
actually break; ``canonicalization.json`` pins exactly that, so it runs as its own
parametrized case set rather than folded into the request vectors.

The graded surface is ``src/core/signing/canonical.py`` — our THIN seam — not
``adcp.signing.canonical`` directly. Asserting straight against the SDK would keep 8
assertions permanently red no matter what we implement, since the divergence is
upstream. The seam's hard boundary::

    REQUEST_TARGET_URI_MALFORMED = "request_target_uri_malformed"
    def reject_malformed_target(url: str) -> None   # the spec's rejection set, and NOTHING else
    def canonical_target_uri(url: str) -> str       # reject_malformed_target(url) then DELEGATE
    def canonical_authority(url: str) -> str        # reject_malformed_target(url) then DELEGATE

It MUST NOT re-derive ``@target-uri`` or ``@authority``. Two canonicalizers in one
verify path is the exact divergence this feature exists to prevent; the seam adds a
gate in front of the SDK and nothing else.

Arithmetic, said out loud so nothing is quietly dropped
------------------------------------------------------
**28 of 31 cases run as conformance through the seam; 3 run as our-obligation
blocker tests with a filed upstream issue. 31 accounted for, 0 skipped, 0 xfailed.**

The 3 are not implementable at OUR boundary:

* ``idn-to-punycode`` and ``idn-mixed-case-to-punycode`` are SIGNER-side.
  ``url-canonicalization.mdx`` step 2: a host containing raw non-ASCII bytes "MUST be
  rejected by the comparer — receivers do not silently re-normalize". The
  punycode-MAPPING half is upstream's; OUR obligation is the REJECTION, and that is
  what the blocker tests below assert. (Same obligation request vector 026 grades.)
* ``trailing-empty-query-preserved`` is unobservable here: ASGI ``query_string`` is
  ``b""`` for both "no query" and "``?``", so our boundary is never handed the
  distinction. Its blocker test PROVES the unobservability instead of asserting a
  behavior we cannot have.

Neither blocker test asserts the SDK's current output. A test that pins today's wrong
answer locks the bug in — that is the one thing this file must never do.

Measured against ``adcp==6.6.0`` (SDK divergence #6, filed upstream): 23 of 31 pass
straight through, and the 8 failures split 5 + 1 + 3 —

* 5 reject cases the SDK ACCEPTS: ``malformed-port-without-host``,
  ``malformed-userinfo-without-host``, ``malformed-empty-authority``,
  ``malformed-bare-ipv6``, ``malformed-ipv6-zone-identifier``;
* 1 reject case the SDK refuses with the WRONG TYPE:
  ``malformed-ipv6-missing-closing-bracket`` raises a bare ``ValueError`` — the seam
  must normalize it, or the case passes on the wrong exception;
* 3 not implementable at our boundary (above).

Error code: the 6 ``reject: true`` cases expect ``request_target_uri_malformed``
(the DATA), grounded at ``url-canonicalization.mdx`` — "Malformed authorities are
rejected with ``request_target_uri_malformed`` on the signing path". The vector
README's worked example is STALE and shows ``request_signature_header_malformed``;
the data wins, so do not "correct" these assertions from the prose. Keep the two
codes apart: request vector ``negative/026`` legitimately expects
``request_signature_header_malformed``. The ``request_target_uri_malformed`` constant
is ABSENT from ``adcp==6.6.0`` (SDK divergence #7), which is why the seam defines it.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers.signing_vectors import load_canonicalization_cases

#: Not implementable at our verifier boundary — each has a named blocker test below.
_UPSTREAM_ONLY = {
    "idn-to-punycode",
    "idn-mixed-case-to-punycode",
    "trailing-empty-query-preserved",
}

_CASES = {case["name"]: case for case in load_canonicalization_cases()}
_CONFORMANCE = sorted(set(_CASES) - _UPSTREAM_ONLY)
_ACCEPT = [name for name in _CONFORMANCE if not _CASES[name].get("reject")]
_REJECT = [name for name in _CONFORMANCE if _CASES[name].get("reject")]


def _seam() -> Any:
    """Import the seam lazily so a missing module fails PER CASE, not at collection."""
    from src.core.signing import canonical

    return canonical


@pytest.mark.parametrize("case_name", _ACCEPT)
def test_canonical_forms_match_the_spec(case_name: str) -> None:
    """The seam's ``@target-uri`` and ``@authority`` equal the spec's canonical bytes."""
    case = _CASES[case_name]
    seam = _seam()

    target = seam.canonical_target_uri(case["input_url"])
    authority = seam.canonical_authority(case["input_url"])

    assert target == case["expected_target_uri"], (
        f"{case_name}: @target-uri diverges. rule: {case['rule']}\n"
        f"  input:    {case['input_url']!r}\n"
        f"  computed: {target!r}\n"
        f"  spec:     {case['expected_target_uri']!r}"
    )
    assert authority == case["expected_authority"], (
        f"{case_name}: @authority diverges. rule: {case['rule']}\n"
        f"  input:    {case['input_url']!r}\n"
        f"  computed: {authority!r}\n"
        f"  spec:     {case['expected_authority']!r}"
    )


@pytest.mark.parametrize("case_name", _REJECT)
def test_malformed_targets_are_rejected_with_the_typed_code(case_name: str) -> None:
    """A malformed authority is REFUSED, and refused with the spec's own code.

    ``expected_error_code`` is ``request_target_uri_malformed`` for all six — a
    DIFFERENT code from ``negative/026``'s ``request_signature_header_malformed``,
    and one ``adcp==6.6.0`` does not define at all.

    ``malformed-ipv6-missing-closing-bracket`` is why the type is asserted and not
    just "something raised": the SDK already refuses that one, but with a bare
    ``ValueError`` — an assertion on refusal alone would pass on the wrong exception.
    """
    case = _CASES[case_name]
    seam = _seam()
    expected_code = case["expected_error_code"]

    for func_name in ("canonical_target_uri", "canonical_authority"):
        with pytest.raises(Exception) as excinfo:  # noqa: B017 — the TYPE is asserted below
            getattr(seam, func_name)(case["input_url"])
        raised = excinfo.value
        assert type(raised) is not ValueError, (
            f"{case_name}: {func_name} refused with a bare ValueError. rule: {case['rule']}. "
            f"The seam must normalize it into the typed {expected_code} error, or this case "
            "passes on the wrong exception."
        )
        assert getattr(raised, "code", None) == expected_code, (
            f"{case_name}: {func_name} raised {type(raised).__name__}(code="
            f"{getattr(raised, 'code', None)!r}), expected code {expected_code!r}. "
            f"rule: {case['rule']}"
        )


def test_the_seam_names_the_spec_code_the_sdk_does_not_define() -> None:
    """``request_target_uri_malformed`` is graded by shipped vectors and absent from the SDK.

    SDK divergence #7. The constant is defined in OUR layer per divergence #2's own
    instruction ("we emit both from our own layer"); this pins the exact string,
    because the string IS the graded artifact.
    """
    assert _seam().REQUEST_TARGET_URI_MALFORMED == "request_target_uri_malformed"


def test_every_canonicalization_case_is_accounted_for() -> None:
    """31 = 28 conformance + 3 named blocker tests. 0 skipped, 0 xfailed."""
    assert len(_CASES) == 31
    assert len(_CONFORMANCE) == 28, sorted(_CONFORMANCE)
    assert _UPSTREAM_ONLY <= set(_CASES)


# ---------------------------------------------------------------------------
# The 3 upstream-only cases, as OUR-obligation blocker tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_name", ["idn-to-punycode", "idn-mixed-case-to-punycode"])
def test_raw_u_label_authority_is_rejected_not_normalized(case_name: str) -> None:
    """OUR obligation for the two IDN cases: REJECT, never re-normalize.

    ``url-canonicalization.mdx`` step 2 — "A host containing raw non-ASCII bytes ...
    MUST be rejected by the comparer — receivers do not silently re-normalize." The
    punycode MAPPING the case's ``expected_target_uri`` asks for is a SIGNER-side
    obligation and is filed upstream (SDK divergence #6); asserting it here would
    demand behavior the spec forbids a verifier from performing.

    This is the same obligation request vector ``negative/026`` grades on the wire.
    """
    case = _CASES[case_name]
    seam = _seam()

    with pytest.raises(Exception) as excinfo:  # noqa: B017 — the code is asserted below
        seam.canonical_authority(case["input_url"])
    assert getattr(excinfo.value, "code", None) == seam.REQUEST_TARGET_URI_MALFORMED, (
        f"{case_name}: a raw U-label authority ({case['input_url']!r}) must be REJECTED by the "
        f"comparer, not silently re-normalized to {case['expected_authority']!r}."
    )


def test_trailing_empty_query_is_unobservable_at_the_asgi_boundary() -> None:
    """``trailing-empty-query-preserved`` cannot be graded here, and this proves why.

    ASGI hands us ``query_string=b""`` for BOTH ``/p`` and ``/p?``: the distinction is
    destroyed before our boundary, so ``_verify_url`` provably cannot preserve it. The
    case is recorded as upstream-only (SDK divergence #6 — ``canonicalize_target_uri``
    drops a trailing empty query) rather than asserted as a behavior we could have.

    Asserted as an EQUALITY between two scopes, not as a truthy check: if a future ASGI
    server or driver ever did carry the distinction, this test fails and the case
    becomes gradeable — which is the outcome we want to be told about.
    """
    from src.core.signing.request_verifier_middleware import _verify_url

    headers = {"host": "seller.example.com"}
    without_query = {"scheme": "https", "path": "/p", "query_string": b"", "raw_path": b"/p"}
    with_empty_query = {"scheme": "https", "path": "/p", "query_string": b"", "raw_path": b"/p?"}

    assert _verify_url(without_query, headers) == _verify_url(with_empty_query, headers), (
        "The trailing '?' became observable at our ASGI boundary. "
        "canonicalization.json's trailing-empty-query-preserved case is now gradeable in-repo "
        "and must be moved out of the upstream-only set."
    )
