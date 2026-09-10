"""The one producer of the credential headers a test presents to this seller.

WHY HERE AND NOT IN tests/harness/. Building a request credential is what every suite
does -- unit, integration, admin, e2e, BDD -- and the harness env is one consumer among
many, not the owner. A second reason keeps it out of that package:
``test_guards_no_adhoc_testclient_bypass`` reads ANY ``tests.harness`` import as "this
test has the harness available", so a test that imports one pure function from there is
required to route its REST calls through the harness too.

Enforced by ``.ast-grep/rules/test-credential-header-single-producer.yml``, which
``make quality-ci`` runs over ``tests/``; graded by
``tests/unit/test_ast_grep_credential_header_ban.py``.
"""

from __future__ import annotations

from typing import Any


def credential_headers(*, token: str | None = None, tenant: str | None = None, dry_run: bool = False) -> dict[str, str]:
    """THE producer: the headers a test presents to this seller, from plain values.

    Every dispatcher, fixture, builder and per-test literal in ``tests/`` builds its
    credential headers here, so a change in what production reads off the wire is one
    edit. Enforced by ``.ast-grep/rules/test-credential-header-single-producer.yml``,
    which ``make quality-ci`` runs; graded by
    ``tests/unit/test_ast_grep_credential_header_ban.py``.

    Production's ``UnifiedAuthMiddleware`` (``src/core/auth_middleware.py``) extracts
    the credential from ``Authorization: Bearer`` for every transport, which is why one
    function serves them all. The ``x-adcp-auth`` alias this used to send is not read:
    pinned 3.1.1 ``L2/authentication.mdx:71`` says the credential MUST ride
    ``Authorization`` and sellers MUST NOT require non-canonical aliases. A caller
    sending the alias presents nothing the seam can see, which surfaces as AUTH_MISSING
    rather than as a header error — 691 of 1013 failures on box run innet_100926_1008.

    Each header is OMITTED when its value is absent, never sent empty: ``token=None``
    dispatches unauthenticated, so the server's own middleware returns the real
    401/``AUTH_MISSING`` rejection instead of one for a malformed credential.

    ``tenant`` is the ``x-adcp-tenant`` value and is a parameter because the two modes
    need different spellings — see :func:`identity_credential_headers`.
    """
    headers: dict[str, str] = {}
    if token is not None:
        # ast-grep-ignore: test-credential-header-single-producer - this IS the one producer
        headers["Authorization"] = f"Bearer {token}"
    if tenant:
        headers["x-adcp-tenant"] = tenant
    if dry_run:
        headers["x-dry-run"] = "true"
    return headers


def identity_credential_headers(identity: Any, *, tenant: str = "subdomain") -> dict[str, str]:
    """:func:`credential_headers` over a resolved identity: the thin adapter.

    ``tenant`` selects which spelling of the tenant goes on the wire, and the two are
    NOT interchangeable. ``"subdomain"`` is right for e2e, where
    ``_detect_tenant`` (``src/core/resolved_identity.py:107``) looks the subdomain up in
    the live database — pinned by ``tests/unit/test_tenant_factory_subdomain.py``.
    ``"tenant_id"`` is right in-process, where no such row exists and ``_detect_tenant``
    falls through to treating the hint as the literal id; feeding it a hyphenated
    subdomain there scopes the principal lookup to a tenant that does not exist.

    ``identity=None`` means "dispatch without credentials" (explicit unauthenticated).
    """
    if identity is None:
        return {}
    if tenant == "subdomain":
        row = getattr(identity, "tenant", None)
        tenant_value = None
        if row is not None:
            tenant_value = row.get("subdomain") if isinstance(row, dict) else getattr(row, "subdomain", None)
    elif tenant == "tenant_id":
        tenant_value = getattr(identity, "tenant_id", None)
    else:
        raise ValueError(f"tenant must be 'subdomain' or 'tenant_id', got {tenant!r}")
    tc = getattr(identity, "testing_context", None)
    return credential_headers(
        token=identity.auth_token,
        tenant=tenant_value,
        dry_run=bool(tc is not None and getattr(tc, "dry_run", False)),
    )
