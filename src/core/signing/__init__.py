"""Our own RFC 9421 signing key material — generation, storage refs, provider resolution.

Scope of this package (salesagent-z6nr.8 / #1291 A2): the keys THIS agent signs
with. Verifying inbound signatures uses the counterparty's keys and lives
elsewhere.

Zero hand-rolled crypto. Key generation, PEM loading, JWK derivation and
signing all come from ``adcp.signing``; what lives here is the lifecycle around
them — which key, for which tenant, at which instant, resolved from which
reference.

Note: ``adcp.signing`` already exports a symbol named ``SigningConfig`` (the
SDK's auto-signing bundle). Ours — :class:`src.core.config.SigningConfig` — is a
different thing. Alias at any import site that touches both.
"""
