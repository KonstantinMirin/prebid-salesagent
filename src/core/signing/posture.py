"""The per-request ``request_signing`` posture — ONE object for advertise and enforce.

#1291 B1 (salesagent-z6nr.12), plan step 1.

``request_signing`` is a *behavioral* declaration: ``covers_content_digest`` and the
six operation buckets are tenant-declared but they change what the VERIFIER does. So
the block the agent advertises on ``get_adcp_capabilities`` and the capability the
verifier enforces must come from one object; two sources is a correctness bug that
advertises a posture we do not enforce (or vice versa).

:class:`RequestSigningPosture` is that object. It extends the AdCP library type — all
eight schema properties, no re-declaration (CLAUDE.md Pattern #1) — and adds the two
derivations the verifier needs:

* :meth:`RequestSigningPosture.bucket_for` — the schema's precedence rule
  ``required_for > warn_for > supported_for``, which is OURS to implement because
  ``adcp.signing.verifier.VerifierCapability`` carries only 4 of the 8 properties and
  only 2 of the 6 buckets: ``warn_for`` and all three ``protocol_methods_*`` are
  SILENTLY DROPPED if handed to the SDK.
* :meth:`RequestSigningPosture.to_verifier_capability` — the lossy projection onto the
  4 fields the SDK does carry, kept in one place so the loss is explicit.

:func:`posture_for_tenant` is the single READER of the tenant declaration, and it is
the seam B1's tests substitute (they replace the declaration, never the middleware's
decision function). D1 (``salesagent-z6nr.20``) populates it and serializes the SAME
object to the wire.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from adcp.signing.verifier import CoversDigestPolicy, VerifierCapability
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import RequestSigning as LibraryRequestSigning
from pydantic import ConfigDict

from src.core.enum_helpers import enum_value
from src.core.schemas.capability_declarations import is_block_declarable

#: The four outcomes the middleware branches on. ``none`` means "signatures are
#: ignored (requests are bearer-authenticated only)" — the schema's own words for
#: ``supported: false``.
PostureBucket = Literal["required", "warn", "supported", "none"]


def _names(items: Any) -> frozenset[str]:
    """Wire-format names from a declared bucket, ``None`` -> empty.

    The ``protocol_methods_*`` buckets are typed as generated enum members while
    ``required_for`` / ``warn_for`` / ``supported_for`` are plain strings; both
    compare against a wire string only through ``.value``.
    """
    if not items:
        return frozenset()
    return frozenset(enum_value(item) for item in items)


def _bucket_for(name: str, required: Any, warn: Any, supported: Any) -> PostureBucket:
    """Apply the schema's ``required_for > warn_for > supported_for`` precedence.

    ``supported_for`` defaulting to ``None`` (rather than ``[]``) is load-bearing and
    is NOT the same as an empty list: an agent that declares ``supported: true`` and
    nothing else verifies signatures wherever they appear — the signed-requests
    storyboard gates all 28 negative vectors on ``request_signing.supported: true``
    alone, so a null ``supported_for`` cannot mean "verify nothing". An explicit list
    narrows that to the operations named.
    """
    if name in _names(required):
        return "required"
    if name in _names(warn):
        return "warn"
    if supported is None:
        return "supported"
    return "supported" if name in _names(supported) else "none"


class RequestSigningPosture(LibraryRequestSigning):
    """A tenant's declared ``request_signing`` block, plus the verifier's two views of it.

    Frozen: one posture is resolved per request and then read by the pre-check, the
    verify call and the outcome branch. A posture that could change between those
    reads would let a request be admitted under one rule and graded under another.
    """

    model_config = ConfigDict(frozen=True)

    def bucket_for(self, operation: str, protocol_method: str | None = None) -> PostureBucket:
        """Which enforcement bucket *operation* (or *protocol_method*) falls in.

        ``protocol_method`` is a JSON-RPC wire method (``tasks/cancel``) and is graded
        against the ``protocol_methods_*`` trio, which the schema keeps as a SEPARATE
        namespace from the AdCP tool names precisely so the two cannot collide as bare
        strings. B2 (``salesagent-z6nr.13``) is what starts supplying it.
        """
        if not self.supported:
            return "none"
        if protocol_method is not None:
            return _bucket_for(
                protocol_method,
                self.protocol_methods_required_for,
                self.protocol_methods_warn_for,
                self.protocol_methods_supported_for,
            )
        return _bucket_for(operation, self.required_for, self.warn_for, self.supported_for)

    def to_verifier_capability(self) -> VerifierCapability:
        """Project onto the 4 fields ``VerifierCapability`` carries.

        Everything else — ``warn_for`` and the three ``protocol_methods_*`` buckets —
        stays HERE, in :meth:`bucket_for`. The SDK reads only ``required_for`` (for its
        absent-header pre-check) and ``covers_content_digest``; handing it the other
        buckets would look like configuration and do nothing.
        """
        return VerifierCapability(
            supported=self.supported,
            covers_content_digest=cast(CoversDigestPolicy, enum_value(self.covers_content_digest) or "either"),
            required_for=_names(self.required_for),
            supported_for=_names(self.supported_for),
        )


#: What every tenant gets today. ``request_signing`` is still in
#: ``_UNBACKED_BLOCKS`` (``src/core/schemas/capability_declarations.py``), so there is
#: no declaration path that can produce anything else — see :func:`posture_for_tenant`.
UNSUPPORTED_POSTURE = RequestSigningPosture(supported=False)


def request_signing_is_declarable() -> bool:
    """Whether any tenant CAN declare a ``request_signing`` posture yet.

    False today: the block is in ``_UNBACKED_BLOCKS``, so every tenant's posture is
    :data:`UNSUPPORTED_POSTURE` no matter what is stored. Callers use this to skip work
    whose result could not change a decision — and because it reads the SAME table
    ``from_tenant`` rejects against, D1 deleting that entry switches them on with no
    second flag to keep in sync.
    """
    return is_block_declarable("request_signing")


def posture_for_tenant(tenant: dict[str, Any] | None) -> RequestSigningPosture:
    """The resolved tenant's declared posture — the ONE reader of that declaration.

    Returns the ``supported=False`` default for every tenant, and that is not a stub:
    ``capability_declarations`` REFUSES a ``request_signing`` block by name
    (``_UNBACKED_BLOCKS``, ``src/core/schemas/capability_declarations.py``), because
    declaring a posture the implementation does not back would promise buyers behavior
    that does not exist. So there is currently no stored value to read, and inventing a
    second parse of the same dict here would create exactly the two-source bug this
    module exists to prevent.

    D1 (``salesagent-z6nr.20``) removes that entry, populates this function from
    ``CapabilityDeclarations.from_tenant(tenant["capability_declarations"])``, and
    serializes the SAME object onto the wire. Until then this is the seam B1's tests
    substitute — they replace the DECLARATION, so production's ``bucket_for``
    precedence still runs for real.
    """
    return UNSUPPORTED_POSTURE
