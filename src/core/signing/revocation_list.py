"""Publish OUR combined revocation list (#1291 A5 follow-up, salesagent-z6nr.27).

security.mdx :1543 is the MUST that binds us: "Signers MUST publish
revocations via the same combined revocation list used for request
signing" — it binds us as a SIGNER of outbound requests and webhooks, not
as the inbound verifier (that half, A5/salesagent-z6nr.11, is complete and
lives in the request-signature middleware). This is the mirror half: the
publisher, next to :mod:`src.core.signing.trust_root`.

Same contract as ``trust_root.py``'s builders: pure functions, no session,
no request, no clock — every input, including ``now``, is passed in, so a
GET twice inside the same quantization bucket returns byte-identical bytes.

**Deliberate divergence from the spec's governance-key profile**
(security.mdx :1079: governance signing keys MUST be served from a separate
origin from transport/webhook keys). This deployment mints exactly one key
purpose (``MINTABLE_PURPOSES`` — request-signing), so the list is signed
with the tenant's REQUEST-SIGNING key, not a governance key. This is
self-consistent with our OWN consumer:
:class:`~src.core.signing.revocation.CounterpartyRevocationChecker` resolves
a published list's ``kid`` through the counterparty's request-signing JWKS,
so our own published list must be resolvable the same way. It is knowingly
NOT the governance profile — see the cross-reference at
``SigningKeyRepository.publishable_at``'s :1079 paragraph, and the follow-up:
``salesagent-z6nr.37``.

**The list's retention is UNBOUNDED where the JWKS grace window is not.** A
kid dropped from ``revoked_kids`` is a kid UN-REVOKED — the schema never
permits removing an entry, only adding one — so this module reads
``SigningKeyRepository.all_revoked()`` (no grace cutoff, ever), never
``publishable_at()`` (which is deliberately time-bound).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from adcp.signing.crypto import b64url_encode, sign_signature_base
from adcp.signing.jws import JWS_ALG_TO_INTERNAL
from adcp.signing.revocation_fetcher import REVOCATION_LIST_TYP

from src.core.agent_identity import canonical_agent_url
from src.core.signing._rfc3339 import rfc3339

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

    from src.core.database.models import SigningKey, Tenant
    from src.core.signing.provider import SigningMaterial

#: The JWS ``alg`` name (what the protected header carries) for each internal
#: algorithm name (what ``SigningMaterial.alg`` / ``sign_signature_base``
#: use) — the inverse of the SDK's own ``JWS_ALG_TO_INTERNAL``. Never
#: hand-maintain a second copy of this mapping.
_JWS_ALG_FOR_INTERNAL: dict[str, str] = {internal: jws_alg for jws_alg, internal in JWS_ALG_TO_INTERNAL.items()}


def build_revocation_list(
    tenant: Tenant,
    revoked_keys: Sequence[SigningKey],
    *,
    now: datetime,
    interval_seconds: int,
) -> dict[str, Any]:
    """The combined revocation list payload — the FIVE members security.mdx
    :1328 names for request-signature governance.

    ``revoked_jtis`` is deliberately OMITTED, not merely unset: :1328 states
    it does not govern request signatures, and this deployment has nothing to
    populate it with.

    ``updated``/``next_update`` are QUANTIZED onto *interval_seconds*
    (``updated = floor(now / interval) * interval``), not read off the raw
    clock: two builds inside the same bucket produce byte-identical output,
    which is what makes the document cacheable and stops every GET from
    looking like a change to a polling consumer. ``version`` is the same
    quantized Unix timestamp — always a positive int, and monotonically
    non-decreasing across buckets by construction, which is all the
    consumer's anti-rollback check requires (it compares ``updated``, not
    ``version``, across refreshes; ``version`` itself is validated only as
    "a positive int" — see ``adcp/signing/revocation_fetcher.py``).
    """
    updated_ts = int(now.timestamp()) // interval_seconds * interval_seconds
    updated = datetime.fromtimestamp(updated_ts, tz=now.tzinfo)
    next_update = updated + timedelta(seconds=interval_seconds)

    return {
        "version": updated_ts,
        "issuer": canonical_agent_url(tenant),
        "updated": rfc3339(updated),
        "next_update": rfc3339(next_update),
        "revoked_kids": [key.kid for key in revoked_keys],
    }


def sign_revocation_list(payload: dict[str, Any], material: SigningMaterial) -> dict[str, Any]:
    """Sign *payload* as a JWS general JSON serialization (RFC 7515 §7.2).

    General JSON, not compact — this is the shape
    ``adcp.signing.jws.parse_general_json_jws`` (and therefore
    ``CachingRevocationChecker``) reads. The protected header carries EXACTLY
    ``alg``/``typ``/``kid`` — no ``crit``, which the SDK's verifier refuses if
    present and non-empty.

    Uses the SDK's own primitives throughout (``b64url_encode``,
    ``sign_signature_base``, ``REVOCATION_LIST_TYP``, the JWS<->internal alg
    mapping) — zero hand-rolled crypto, per this layer's standing rule.
    """
    header = {
        "alg": _JWS_ALG_FOR_INTERNAL[material.alg],
        "typ": REVOCATION_LIST_TYP,
        "kid": material.kid,
    }
    b64_protected = b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    b64_payload = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    # RFC 7515 §5.1: the signing input is the two base64url STRINGS joined by
    # a dot — never a decode-and-re-encode of either segment.
    signing_input = f"{b64_protected}.{b64_payload}".encode("ascii")
    signature = sign_signature_base(alg=material.alg, private_key=material.private_key, signature_base=signing_input)

    return {
        "payload": b64_payload,
        "signatures": [
            {
                "protected": b64_protected,
                "signature": b64url_encode(signature),
            }
        ],
    }
