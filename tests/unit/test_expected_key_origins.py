"""What the verifier pins the resolved JWKS against, per counterparty declaration.

``identity.key_origins`` has THREE states and the verifier used to tell apart only two.
``resolution.key_origins or {}`` collapsed "advertised no map at all" into "advertised an
empty map", and the SDK treats those identically: ``adcp/signing/key_origins.py`` reads
``declared = (key_origins or {}).get(purpose)`` and raises
``request_signature_key_origin_missing`` when it is ``None``. It takes a ``posture``
argument and uses it only to decorate the message, so the refusal is NOT conditioned on
the counterparty having declared a signing posture.

security.mdx @ v3.1.1 conditions it on exactly that, and says an ABSENT map means
shared-origin. The capabilities schema admits ``identity.key_origins.request_signing``
only for an agent that declares ``request_signing`` buckets — so a buyer who signs but
does not verify could not comply either way: it may not declare the entry, and we refused
it for not declaring the entry.

These three cases are the fix. The middle one is the pre-existing behaviour and must not
move; the last one is what changed.
"""

from __future__ import annotations

from adcp.signing.agent_resolver import AgentResolution

from src.core.signing.verifier import _expected_key_origins

_JWKS = "https://keys.brand.example/.well-known/jwks.json"
_BRAND = "https://brand.example/.well-known/brand.json"


def _resolution(key_origins: dict[str, str] | None) -> AgentResolution:
    """A resolution carrying *key_origins*, everything else fixed and irrelevant here."""
    return AgentResolution(
        agent_url="https://agent.example/mcp/",
        brand_json_url=_BRAND,
        agent_entry={"type": "sales", "url": "https://agent.example/mcp/", "jwks_uri": _JWKS},
        jwks_uri=_JWKS,
        jwks={"keys": []},
        fetched_at=0.0,
        key_origins=key_origins,
    )


def test_a_declared_map_is_passed_through_unchanged() -> None:
    """The counterparty published an origin for our purpose; pin against exactly that."""
    declared = {"request_signing": "https://keys.brand.example"}

    assert _expected_key_origins(_resolution(declared)) == declared


def test_a_map_without_our_purpose_still_reaches_the_sdk_and_is_refused() -> None:
    """Declared-but-silent-about-request_signing is NOT the same as undeclared.

    A counterparty that published a map and omitted our purpose has said something, and
    what it said is not "anywhere". Passing the map through unchanged is what lets the SDK
    answer ``request_signature_key_origin_missing`` — the behaviour that must not move.
    """
    declared = {"webhook_signing": "https://hooks.brand.example"}

    assert _expected_key_origins(_resolution(declared)) == declared
    assert "request_signing" not in _expected_key_origins(_resolution(declared))


def test_no_map_at_all_assumes_the_brand_json_origin() -> None:
    """The spec's shared-origin default, made explicit rather than left unmade.

    This is the case that changed. ``None`` means the counterparty advertised no map,
    which v3.1.1 reads as shared-origin — so the JWKS must come from the same origin as
    the brand.json, and that is what gets pinned. Passing ``None`` to the SDK instead
    would SKIP the check with a warning, losing the shared-tenancy defence entirely.
    """
    assert _expected_key_origins(_resolution(None)) == {"request_signing": "https://brand.example"}


def test_no_resolution_pins_nothing() -> None:
    """No counterparty resolved, so there is no origin to pin and nothing to assume."""
    assert _expected_key_origins(None) is None
