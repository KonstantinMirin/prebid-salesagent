"""The per-request ``request_signing`` posture — ONE object for advertise and enforce.

#1291 B1, re-homed onto #1721's request boundary.

``request_signing`` is a *behavioral* declaration: ``covers_content_digest`` and the six
operation buckets are tenant-declared but they change what the VERIFIER does. So the
block the agent advertises on ``get_adcp_capabilities`` and the capability the verifier
enforces must come from one object; two sources is a correctness bug that advertises a
posture we do not enforce (or vice versa).

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

:func:`posture_for_tenant` is the single READER of the tenant declaration, and it now
takes the loaded :class:`~src.core.tenant_context.TenantContext` the resolver already
holds. On the pre-merge branch it took a ``PostureTenant`` TypedDict projected out of a
second, verifier-owned tenant lookup (``_detect_tenant_for_posture``) that existed only
because the ASGI middleware ran BEFORE identity resolution. Inside ``_resolve_identity``
there is exactly one tenant read, so the projection, the second lookup and the
swallow-everything failure mode around it are all deleted.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, cast

from adcp.signing.verifier import CoversDigestPolicy, VerifierCapability
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import RequestSigning as LibraryRequestSigning
from pydantic import ConfigDict, RootModel

from src.core.enum_helpers import enum_value

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module free of DB imports
    from src.core.schemas.capability_declarations import CapabilityDeclarations
    from src.core.tenant_context import TenantContext

logger = logging.getLogger(__name__)

#: The four outcomes the verifier branches on. ``none`` means "signatures are ignored
#: (requests are bearer-authenticated only)" — the schema's own words for
#: ``supported: false``.
PostureBucket = Literal["required", "warn", "supported", "none"]


def _name(item: Any) -> str:
    """The wire string a single declared bucket entry compares against.

    The three ``protocol_methods_*`` buckets are typed as generated ``RootModel[str]``
    wrappers (``ProtocolMethodsRequiredForItem`` and siblings, each carrying the
    ``^[a-z][a-z0-9_]*/[a-z][a-z0-9_]*$`` pattern), while ``required_for`` / ``warn_for``
    / ``supported_for`` are plain strings. The wrappers are NOT enums, so ``enum_value``
    falls through to ``str(v)`` and yields ``"root='tasks/cancel'"`` — a frozenset that
    matches no wire method, i.e. silently zero enforcement for any tenant declaring a
    protocol-method bucket.

    The unwrap is typed on :class:`pydantic.RootModel` rather than a defensive attribute
    probe, which is both wrong (it would swallow a genuine shape change) and forbidden by
    ``test_architecture_no_defensive_rootmodel``.
    """
    if isinstance(item, RootModel):
        return str(item.root)
    return enum_value(item)


#: One declared bucket as it arrives off the wire. Named rather than left as ``Any`` so
#: the call sites state what they accept — and the members are NOT uniform, which is
#: exactly what :func:`_name` exists to flatten.
type DeclaredBucket = Iterable[str | Enum | RootModel[str]] | None


def bucket_names(items: DeclaredBucket) -> frozenset[str]:
    """Wire-format names from a declared bucket, ``None`` -> empty."""
    if not items:
        return frozenset()
    return frozenset(_name(item) for item in items)


def _bucket_for(name: str, required: Any, warn: Any, supported: Any) -> PostureBucket:
    """Apply the schema's ``required_for > warn_for > supported_for`` precedence.

    ``supported_for`` defaulting to ``None`` (rather than ``[]``) is load-bearing and is
    NOT the same as an empty list: an agent that declares ``supported: true`` and nothing
    else verifies signatures wherever they appear — the signed-requests storyboard gates
    all 28 negative vectors on ``request_signing.supported: true`` alone, so a null
    ``supported_for`` cannot mean "verify nothing". An explicit list narrows that to the
    operations named.
    """
    if name in bucket_names(required):
        return "required"
    if name in bucket_names(warn):
        return "warn"
    if supported is None:
        return "supported"
    return "supported" if name in bucket_names(supported) else "none"


class RequestSigningPosture(LibraryRequestSigning):
    """A tenant's declared ``request_signing`` block, plus the verifier's two views of it.

    Frozen: one posture is resolved per request and then read by the pre-check, the verify
    call and the outcome branch. A posture that could change between those reads would let
    a request be admitted under one rule and graded under another.

    THE NAMESPACE SPLIT IS NOT ENFORCED HERE. It was, on the pre-merge branch, as a
    ``model_validator`` testing every AdCP-bucket entry for a ``/``. Two things were wrong
    with that. It decided tool-ness by looking for a slash, which is a second definition of
    a question ``src.core.tools.registry`` owns; and a type-level validator cannot express
    the other half of the rule (an AdCP tool name appearing in a ``protocol_methods_*``
    bucket) in a way an operator can act on, because by the time a validator runs pydantic
    has already refused the string with a regex message. Both halves now live in one place,
    ``src.core.schemas.capability_declarations._reject_mixed_namespaces``, which runs on the
    RAW declaration and is the config-time rejection security.mdx @ v3.1.1 :1053 requires.
    """

    model_config = ConfigDict(frozen=True)

    def bucket_for(self, operation: str, protocol_method: str | None = None) -> PostureBucket:
        """Which enforcement bucket *operation* (or *protocol_method*) falls in.

        THE cross-namespace rule, security.mdx @ v3.1.1 :1053:

            Verifiers MUST NOT cross-namespace match: a ``protocol_methods_required_for``
            membership MUST NOT be satisfied by a body whose JSON-RPC ``method`` is
            ``tools/call`` (even if ``params.name`` happens to equal a listed method
            string) ... The two buckets are matched against disjoint envelope fields.

        Which is why the two arguments are mutually exclusive and the caller supplies the
        ENVELOPE's method, never the resolved tool name. ``protocol_method=None`` says "the
        envelope named an AdCP operation", and then the ``protocol_methods_*`` trio is not
        consulted at all — so a tenant declaring ``protocol_methods_required_for:
        ["tasks/cancel"]`` cannot have it satisfied by an operation that happens to carry
        the same string. The shortcut of grading the resolved tool name against both tries
        looks more informative and is a conformance failure.
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
            required_for=bucket_names(self.required_for),
            supported_for=bucket_names(self.supported_for),
        )


#: The posture of an agent that does not verify at all: ``supported: false`` puts every
#: operation in the ``none`` bucket. Reached two ways — the verifier kill switch is off
#: (:func:`agent_level_posture`), or a tenant's declaration cannot be read.
UNSUPPORTED_POSTURE = RequestSigningPosture(supported=False)


def request_signing_is_declarable() -> bool:
    """Whether any tenant CAN declare a ``request_signing`` posture.

    Callers use it to skip work whose result could not change a decision, and because it
    reads the SAME table ``from_tenant`` rejects against, re-adding the block to
    ``_UNBACKED_BLOCKS`` switches them off by itself with no second flag to keep in sync.
    """
    from src.core.schemas.capability_declarations import is_block_declarable

    return is_block_declarable("request_signing")


def agent_level_posture() -> RequestSigningPosture:
    """The posture a tenant that declared nothing honestly holds.

    ``supported`` is ``SigningConfig.verifier_enabled`` and every bucket is EMPTY. Both
    halves are the pin's, not a convenience:

    * v3.1.1 ``get-adcp-capabilities-response.json`` defines ``request_signing.supported``
      as "Whether this agent VERIFIES RFC 9421 signatures on incoming requests" — an
      AGENT-level fact. The verifier runs inside ``_resolve_identity``, which every
      transport reaches, so a literal ``false`` UNDER-declares something true, which is
      the same dishonesty as an over-declaration pointed the other way.
    * ``required_for`` is "empty in 3.0 by default; sellers populate selectively during
      per-counterparty pilots". A non-empty default would reject every existing buyer at
      once.
    """
    from src.core.config import get_settings

    return RequestSigningPosture(supported=get_settings().signing.verifier_enabled)


def posture_from_declarations(declarations: CapabilityDeclarations | None) -> RequestSigningPosture:
    """The posture *declarations* resolves to — the ONE declaration -> posture mapping.

    An undeclared posture falls back to :func:`agent_level_posture`. A DECLARED one still
    degrades to ``supported=False`` when agent-level backing is absent: the verifier
    really is not running, and because this is ONE object the wire then also says so.
    Rolling the verifier back is therefore a flag flip that makes the wire honest, not one
    that turns discovery into an error for every tenant that changed nothing.
    """
    from src.core.config import get_settings

    declared = declarations.request_signing if declarations else None
    if declared is None:
        return agent_level_posture()
    if not get_settings().signing.verifier_enabled:
        logger.warning(
            "Tenant declared a request_signing posture but SigningConfig.verifier_enabled is "
            "false, so no inbound verification runs; advertising and enforcing supported=false "
            "instead of a posture nothing backs"
        )
        return UNSUPPORTED_POSTURE
    return declared


def posture_for_tenant(tenant: TenantContext | None) -> RequestSigningPosture:
    """The resolved tenant's declared posture — the ONE reader of that declaration.

    Parses ``tenant.capability_declarations`` through the store and projects it with
    :func:`posture_from_declarations`, so the block serialized onto the
    ``get_adcp_capabilities`` wire and the :class:`VerifierCapability` the verifier
    enforces are two views of one object.

    ``AdCPSalesAgentError`` is caught HERE and downgraded to :data:`UNSUPPORTED_POSTURE`,
    with a WARNING naming the tenant. An unreadable declaration is a seller
    misconfiguration, and the same misconfiguration IS a terminal CONFIGURATION_ERROR on
    ``get_adcp_capabilities``, which parses the store itself — loud where it belongs. What
    the fallback must not do is INVENT enforcement the tenant never declared: promoting an
    unreadable declaration to ``required`` turns a config typo into a 401 on every AdCP
    surface. Never a bare ``except Exception``, which would hide a genuine bug as a
    silently unenforced posture.

    The ``None`` case is reachable only where no tenant resolved at all. Inside
    ``_resolve_identity`` that is a request whose Host names no tenant, which cannot
    resolve a principal either, so nothing per-tenant could have been enforced for it.
    """
    from src.core.exceptions import AdCPSalesAgentError
    from src.core.schemas.capability_declarations import CapabilityDeclarations

    if tenant is None:
        return agent_level_posture()
    try:
        declarations = CapabilityDeclarations.from_tenant(tenant.capability_declarations)
    except AdCPSalesAgentError as exc:
        logger.warning(
            "Tenant %r has an unreadable capability declaration, so its request_signing posture "
            "cannot be resolved and nothing is enforced for it: %s",
            tenant.tenant_id,
            exc,
        )
        return UNSUPPORTED_POSTURE
    return posture_from_declarations(declarations)


def request_signing_buckets_declared(posture: RequestSigningPosture) -> bool:
    """Whether *posture* names any operation or protocol method in any bucket.

    The pin's ``key_origins`` ``purpose_anchoring`` constraint and the
    ``identity.brand_json_url`` ``required_when`` trigger list: a declared bucket
    "requires non-empty ``request_signing.supported_for``/``required_for``/
    ``protocol_methods_supported_for``/``protocol_methods_required_for``". ``warn_for`` is
    deliberately NOT in that list — the pin's, not an omission here.
    """
    return any(
        bucket_names(bucket)
        for bucket in (
            posture.supported_for,
            posture.required_for,
            posture.protocol_methods_supported_for,
            posture.protocol_methods_required_for,
        )
    )
