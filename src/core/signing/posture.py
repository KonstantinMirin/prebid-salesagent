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

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast

from adcp.signing.verifier import CoversDigestPolicy, VerifierCapability
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import RequestSigning as LibraryRequestSigning
from pydantic import ConfigDict, RootModel, model_validator

from src.core.enum_helpers import enum_value
from src.core.schemas.capability_declarations import is_block_declarable

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module free of DB imports
    from src.core.database.repositories.signing_key import SigningKeyRepository

#: The four outcomes the middleware branches on. ``none`` means "signatures are
#: ignored (requests are bearer-authenticated only)" — the schema's own words for
#: ``supported: false``.
PostureBucket = Literal["required", "warn", "supported", "none"]


def _name(item: Any) -> str:
    """The wire string a single declared bucket entry compares against.

    The three ``protocol_methods_*`` buckets are typed as generated
    ``RootModel[str]`` wrappers (``ProtocolMethodsRequiredForItem`` and siblings,
    each carrying the ``^[a-z][a-z0-9_]*/[a-z][a-z0-9_]*$`` pattern), while
    ``required_for`` / ``warn_for`` / ``supported_for`` are plain strings. The
    wrappers are NOT enums, so ``enum_value`` falls through to ``str(v)`` and
    yields ``"root='tasks/cancel'"`` — a frozenset that matches no wire method,
    i.e. silently zero enforcement for any tenant declaring a protocol-method
    bucket. B1 could not see it because ``UnresolvedOperationResolver`` never
    supplied a protocol method; B2 is what makes the branch reachable.

    The unwrap is typed on :class:`pydantic.RootModel` rather than a defensive
    attribute probe, which is both wrong (it would swallow a genuine shape change)
    and forbidden by ``test_architecture_no_defensive_rootmodel``.
    """
    if isinstance(item, RootModel):
        return str(item.root)
    return enum_value(item)


def _names(items: Any) -> frozenset[str]:
    """Wire-format names from a declared bucket, ``None`` -> empty."""
    if not items:
        return frozenset()
    return frozenset(_name(item) for item in items)


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

    @model_validator(mode="after")
    def _namespaces_must_not_be_mixed(self) -> RequestSigningPosture:
        """Reject a declaration that puts a JSON-RPC method in an AdCP bucket.

        security.mdx :1045-1059 — the schema's own words on ``required_for``: "Not MCP
        tool names, A2A skill names, or any transport-specific rename … JSON-RPC
        protocol method names like ``tasks/cancel`` belong in
        ``protocol_methods_required_for``, not here", and :1053 requires a
        CONFIGURATION-time rejection rather than coercion.

        Only this direction needs enforcing here: the ``protocol_methods_*`` items are
        generated ``RootModel``s carrying the ``^[a-z][a-z0-9_]*/…`` pattern, so
        pydantic already refuses a slash-free AdCP name in them. Nothing enforced the
        reverse, and nothing could observe it either, until B2 started naming requests
        in both namespaces.

        D1 (``salesagent-z6nr.20``) feeds this real tenant declarations and owns the
        remaining declaration-time rules (the ``x-adcp-validation`` subset/disjoint
        checks, and a warning for a ``protocol_methods_*`` entry naming
        ``message/send``, which explicit-skill A2A calls can never satisfy).
        """
        mixed = sorted(
            name
            for bucket in (self.required_for, self.warn_for, self.supported_for)
            for name in _names(bucket)
            if "/" in name
        )
        if mixed:
            raise ValueError(
                f"request_signing operation buckets name JSON-RPC protocol methods: {mixed}. "
                "required_for / warn_for / supported_for carry AdCP operation names only; "
                "a name containing '/' belongs in the matching protocol_methods_* bucket "
                "(get-adcp-capabilities-response.json, security.mdx :1045-1059)."
            )
        return self

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


class KeyBacking(NamedTuple):
    """What this tenant's own signing keys let it honestly declare.

    THE single key-presence derivation. Both C1's outbound signer
    (``salesagent-z6nr.18``) and D1's declaration builder (``salesagent-z6nr.20``)
    consume this one — a second derivation of "does this tenant have a key" is
    how the advertised posture and the enforced one drift apart, which is the
    whole reason this module exists.

    Two fields rather than one, because the facts they back sit on opposite sides
    of a distinction the repository calls load-bearing
    (``SigningKeyRepository.active_at`` vs ``publishable_at``):

    ======================================  ===============================  ================
    field                                   means                            selector
    ======================================  ===============================  ================
    ``signs`` -> ``webhook_signing``        this agent SIGNS                 ``active_at``
    ``publishes`` -> ``identity``           this agent PUBLISHES             ``publishable_at``
    ======================================  ===============================  ================

    A key inside its revocation grace window, or one with a future
    ``not_before``, is publishable but not active. Collapsing the two would push
    the choice down a layer into whichever consumer guessed first.
    """

    signs: bool
    publishes: bool


def signing_key_backed(repo: SigningKeyRepository, *, now: datetime) -> KeyBacking:
    """Whether *repo*'s tenant has key material backing each declared fact.

    Takes a repository and opens NO session: the transport (the admin blueprint,
    the setup checklist, D1's capabilities builder) already owns one, and a
    per-call unit of work inside this module would add a second session to a
    capabilities request that already holds one.

    It does NOT back ``request_signing``. That block declares whether this agent
    VERIFIES signatures on INCOMING requests, which uses the COUNTERPARTY's keys
    — it is backed by ``SigningConfig.verifier_enabled`` plus the mounted
    ``RequestSignatureMiddleware``, and is completely independent of whether this
    tenant owns a key of its own. The asymmetry is the spec's: v3.1.1
    ``get-adcp-capabilities-response.json`` defines ``request_signing.supported``
    as "Whether this agent VERIFIES RFC 9421 signatures on incoming requests" and
    ``webhook_signing.supported`` as "Whether this agent SIGNS outbound webhooks".
    """
    from src.core.config import get_config

    return KeyBacking(
        signs=repo.active_at(now=now) is not None,
        publishes=bool(repo.publishable_at(now=now, grace_seconds=get_config().signing.grace_seconds)),
    )
