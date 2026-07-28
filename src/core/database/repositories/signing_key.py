"""Tenant-scoped access to this agent's own RFC 9421 signing keys.

Backs #1291 A2 (salesagent-z6nr.8). Every ``select(SigningKey)`` in the codebase
lives here — the structural guard forbids raw model queries outside the
repository layer, and the tenant scope is exactly what a stray query would drop.

Two selectors, and the difference matters:

* :meth:`active_at` — which key we SIGN with at an instant. Governed by the
  ``[not_before, not_after)`` window plus ``revoked_at``.
* :meth:`publishable_at` — which keys we PUBLISH at an instant. Governed by
  ``revoked_at`` plus the ``agent-signing-key`` schema's grace period, and by
  NEITHER window bound. Publication is window-blind by design.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from src.core.database.models import SigningKey
from src.core.signing.algorithms import REQUEST_SIGNING


class SigningKeyRepository:
    """Tenant-scoped CRUD for ``signing_keys``.

    Args:
        session: SQLAlchemy session (caller manages lifecycle).
        tenant_id: Tenant scope for all queries.
    """

    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def _scope_prefix(self) -> tuple[ColumnElement[bool], ...]:
        """The tenant isolation term EVERY query composes.

        One home for the scope so an isolation fix lands once rather than once
        per query — a missed copy would silently publish or sign with another
        tenant's key material.
        """
        return (SigningKey.tenant_id == self._tenant_id,)

    def get_by_kid(self, kid: str) -> SigningKey | None:
        """Return this tenant's key with *kid*, or None.

        ``UNIQUE(tenant_id, kid)`` makes this at most one row. This is the
        resolution path when a caller designates a specific key — the mechanism
        that lets one signing surface use a different key from another
        (security.mdx: "isolation comes from the kid").
        """
        stmt = select(SigningKey).where(*self._scope_prefix(), SigningKey.kid == kid).limit(1)
        return self._session.scalars(stmt).first()

    def active_at(self, *, now: datetime, purpose: str = REQUEST_SIGNING) -> SigningKey | None:
        """Return the key to sign *purpose* with at *now*, or None.

        The window is half-open ``[not_before, not_after)`` — inclusive lower
        bound, exclusive upper — and ``not_after IS NULL`` reads as +infinity.
        The current key is always open-ended, so a NULL-blind predicate would
        leave every tenant with no signable key at all.

        ``revoked_at`` beats the window: a revoked open-ended key would otherwise
        resolve forever, since its window never closes.

        When rotation leaves two keys active, the newest signs. The tie-break is
        total (``created_at DESC, kid ASC``) so two rows created in one
        transaction cannot produce a nondeterministic signer.
        """
        stmt = (
            select(SigningKey)
            .where(
                *self._scope_prefix(),
                SigningKey.purpose == purpose,
                SigningKey.revoked_at.is_(None),
                SigningKey.not_before <= now,
                or_(SigningKey.not_after.is_(None), SigningKey.not_after > now),
            )
            .order_by(SigningKey.created_at.desc(), SigningKey.kid.asc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def publishable_at(
        self, *, now: datetime, grace_seconds: float, purpose: str = REQUEST_SIGNING
    ) -> list[SigningKey]:
        """Return every key to PUBLISH for *purpose* at *now*.

        Mirrors :meth:`active_at`'s scope and ordering, minus the window — and
        the omission is the whole point:

        * **Never ``not_after``.** Un-publishing a key whose window has closed
          strands every signature it made that is still inside its verification
          window — the exact gap rotation overlap exists to prevent.
        * **Never ``not_before``.** Rotation must publish the incoming key
          BEFORE it signs, so that every verifier's cache already holds it when
          the first signature arrives.

        Consequence, and it is a REQUIREMENT on callers rather than a caveat:
        **retirement MUST set ``revoked_at``** (:meth:`revoke`). Closing the
        window retires a SIGNER; it never retires a PUBLICATION, so a key
        retired only by ``not_after`` would be published forever.

        ``revoked_at`` is the sole exit, and it is delayed by *grace_seconds*:
        ``core/agent-signing-key.json`` says a revoked key "MAY continue to
        appear in the trust anchor during a grace period so caches that have not
        yet refreshed still find the key and can evaluate the revocation
        marker", and may be removed "once the cache TTL ... has elapsed across
        all verifiers". The published documents carry the marker for exactly
        that reason.

        *purpose* is filtered because ``security.mdx``:1079 forbids co-tenanting
        purposes in one JWKS ("governance signing keys MUST be served from a
        separate origin"). Latent today — ``MINTABLE_PURPOSES`` holds one value
        — and a latent violation of a MUST is still one.
        """
        cutoff = now - timedelta(seconds=grace_seconds)
        stmt = (
            select(SigningKey)
            .where(
                *self._scope_prefix(),
                SigningKey.purpose == purpose,
                or_(SigningKey.revoked_at.is_(None), SigningKey.revoked_at > cutoff),
            )
            .order_by(SigningKey.created_at.desc(), SigningKey.kid.asc())
        )
        return list(self._session.scalars(stmt).all())

    def create_from_keypair(
        self,
        *,
        kid: str,
        alg: str,
        purpose: str,
        public_jwk: dict[str, Any],
        private_key_ref: str,
        not_before: datetime,
        not_after: datetime | None = None,
    ) -> SigningKey:
        """Persist a freshly minted keypair's public half and private-key reference.

        The SOLE construction site for ``SigningKey`` — no ORM kwargs are
        assembled at a call site. ``private_key_ref`` is a scheme-prefixed
        reference (``env:NAME`` / ``file:/abs/path``); passing key material here
        is what this repository exists to prevent.

        ``not_after`` defaults to NULL: a newly provisioned key is the current
        key and the current key is open-ended. Retirement is a later ``revoke``
        or an explicit window close, never a birth-time expiry.
        """
        key = SigningKey(
            id=f"sk_{uuid4().hex[:16]}",
            tenant_id=self._tenant_id,
            kid=kid,
            alg=alg,
            purpose=purpose,
            public_jwk=public_jwk,
            private_key_ref=private_key_ref,
            not_before=not_before,
            not_after=not_after,
        )
        self._session.add(key)
        self._session.flush()
        return key

    def revoke(self, kid: str, *, at: datetime) -> SigningKey | None:
        """Stamp ``revoked_at`` on this tenant's key *kid* and return it.

        The transition, so no caller hand-sets the column. Revocation is what
        retires an open-ended key — closing the window cannot, because the
        current key has no upper bound.
        """
        key = self.get_by_kid(kid)
        if key is None:
            return None
        key.revoked_at = at
        self._session.flush()
        return key
