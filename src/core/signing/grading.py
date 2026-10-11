"""A tenant's declaration that it is a ``signed_requests`` grading target.

THE LAYER'S SECOND DEPENDENCY-FREE LEAF, beside :mod:`.algorithms`: it imports only
pydantic, so ``src.core.database.models`` can type the ``tenants.signed_requests_grading``
column with it without pulling the verifier in behind it.

The signed-requests test kit (``dist/compliance/3.1.1/test-kits/signed-requests-runner.yaml``
at AdCP 3.1.1) asks the agent under test to pre-configure three relaxations "for the
test-kit counterparty only" (L32-34, L55-60, L146-149): an accepted JWKS holding the kit's
published keys, a per-keyid replay cap far below the production floor (L108-126), and a
replay-row lifetime short enough to drain between vectors (L76-92). All three weaken a
protection, and the kit's private keys are public, so where they may exist is the whole
question.

They exist on this record and nowhere else. A tenant carrying one has declared itself a
grading target; a tenant without one has no test-kit trust at all, and no principal or
keyid row has a field that could hold any of the three. :meth:`SignedRequestsGrading.for_keyid`
is the one place the codebase decides whether a request's keyid is the kit's on a tenant.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: runner.yaml ``stateful_vector_contract.replay.min_replay_ttl_seconds``: a replay row
#: living less than this lets the second submission of vector 016 arrive after the first
#: was forgotten, so the vector passes without the replay check running.
MIN_REPLAY_TTL_SECONDS = 10


class SignedRequestsGrading(BaseModel):
    """The test-kit relaxations one grading tenant grants to the kit's keyids.

    ``jwks`` is the kit's public key set. The verifier verifies a bearer-less request whose
    keyid is in it against these keys, because the kit's counterparty has no origin to walk.
    The JWKs stay dicts: checklist step 8 reads ``use``, ``key_ops`` and ``adcp_use``, which
    the SDK's ``AgentSigningKey`` does not declare.

    ``replay_cap`` and ``replay_ttl_seconds`` tune the replay store for the kit's keyids,
    whatever the credential, because the spec's step 9a cap is per keyid and the kit defines
    its counterparty by its keyids.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    jwks: dict[str, Any]
    replay_cap: int | None = Field(default=None, gt=0)
    replay_ttl_seconds: float | None = Field(default=None, ge=MIN_REPLAY_TTL_SECONDS)

    @field_validator("jwks")
    @classmethod
    def _keys_name_unique_kids(cls, jwks: dict[str, Any]) -> dict[str, Any]:
        """A non-empty ``keys`` list whose every key names a distinct, non-empty ``kid``.

        The kid is how :meth:`for_keyid` matches and how the checklist selects a key, so a
        key without one could never be used and two keys sharing one would make the key a
        signature verifies against depend on list order.
        """
        keys = jwks.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("jwks must carry a non-empty 'keys' list")
        kids = [key.get("kid") if isinstance(key, dict) else None for key in keys]
        if not all(isinstance(kid, str) and kid for kid in kids):
            raise ValueError("every key in jwks must name a non-empty string 'kid'")
        if len(set(kids)) != len(kids):
            raise ValueError(f"jwks names a kid more than once: {kids!r}")
        return jwks

    def for_keyid(self, keyid: str | None) -> SignedRequestsGrading | None:
        """This record when *keyid* is the ``kid`` of one of its keys, else ``None``.

        The one decision of whether a request's keyid is the kit's on this tenant. The
        verifier asks it once per request, on the keyid of the label the checklist verifies,
        and hands the answer to everything that depends on it.
        """
        if keyid is None:
            return None
        return self if any(key["kid"] == keyid for key in self.jwks["keys"]) else None
