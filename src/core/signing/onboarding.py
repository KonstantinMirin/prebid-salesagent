"""The request-signing record a counterparty is onboarded with: ``principals.request_signing``.

A signed request that presents no bearer has one handle, its ``keyid``. security.mdx @
v3.1.1 :1090 lets the verifier resolve the signer from "prior onboarding", and :1094 forbids
accepting a ``keyid`` it cannot resolve to a specific ``agents[]`` entry. This record is that
onboarding: the counterparty's JWKS, pinned on the principal whose ``agent_url`` is the
``agents[]`` mapping (:1210-1216). The verifier resolves a bearer-less ``keyid`` against the
records of the tenant the request addressed, never across tenants.

The two replay fields are the signed-requests test kit's per-counterparty tuning
(``dist/compliance/3.1.1/test-kits/signed-requests-runner.yaml`` :113-149: a lower per-keyid
cap and a replay TTL "for the test-kit counterparty only"). The deployment-wide cap
(``SigningSettings.per_keyid_cap``) keeps its production floor; a lower cap exists only here.

A dependency-free leaf, like :mod:`src.core.signing.algorithms`, so the ORM model can type
its column with it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestSigningRecord(BaseModel):
    """One counterparty's pinned request-signing keys and its replay tuning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: The counterparty's public JWKS, pinned at onboarding.
    jwks: dict[str, Any]
    #: Live replay entries per keyid before ``request_signature_rate_abuse``; the deployment
    #: cap when unset.
    replay_cap: int | None = Field(default=None, gt=0)
    #: Upper bound on a replay row's lifetime for this counterparty's keyids; the
    #: signature's own window when unset.
    replay_ttl_seconds: float | None = Field(default=None, gt=0)

    @field_validator("jwks")
    @classmethod
    def validate_jwks(cls, jwks: dict[str, Any]) -> dict[str, Any]:
        """Every key names a distinct ``kid`` and carries no private member.

        The ``kid`` is the lookup key (``PrincipalRepository.find_by_signing_keyid``), so a
        key without one could never be selected and a repeated one would resolve to two keys.
        """
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("jwks must carry a non-empty 'keys' list")
        kids = [key.get("kid") if isinstance(key, dict) else None for key in keys]
        if not all(isinstance(kid, str) and kid for kid in kids):
            raise ValueError("every pinned key must name its kid")
        if len(set(kids)) != len(kids):
            raise ValueError("a kid must name exactly one pinned key")
        if any("d" in key for key in keys):
            raise ValueError("pinned keys are public keys; a JWK carrying 'd' is private material")
        return jwks
