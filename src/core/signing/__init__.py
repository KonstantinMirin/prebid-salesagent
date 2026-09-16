"""Inbound RFC 9421 request-signature verification (#1291 B1-B4), on #1721's boundary.

DELIBERATELY EMPTY. Every module here is imported by its own dotted path, and that is
what keeps the layer's import graph acyclic without a PEP 562 lazy-export table:
``src.core.metrics`` reads :mod:`src.core.signing.vocabulary` to bound an
attacker-chosen Prometheus label, and :mod:`src.core.signing.verifier` reads
``src.core.metrics``. A facade re-exporting either would close that cycle at import
time, which is what the separate ``src.core.signing_contract`` package existed to
break on the pre-merge branch. With no re-exports there is nothing to break.

Where each piece lives:

===========================  =========================================================
:mod:`.vocabulary`           every name an operation label can carry, derived from TOOLS
:mod:`.canonical`            the URL-canonicalization seam (comparer side)
:mod:`.operations`           the webhook-credential escalation read off a request body
:mod:`.posture`              a tenant's declared ``request_signing`` block
:mod:`.replay_store`         the Postgres-backed nonce store the SDK checklist calls
:mod:`.revocation`           checklist step 9, the counterparty's revocation list
:mod:`.verifier`             THE verifier, called by ``_resolve_identity``
===========================  =========================================================
"""
