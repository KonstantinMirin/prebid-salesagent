"""Format resolution with product overrides and dynamic creative agent discovery.

Provides layered format lookup:
1. Product-level overrides (from product.implementation_config.format_overrides)
2. Dynamic format discovery from creative agents (via CreativeAgentRegistry)

Note: Tenant custom formats (creative_formats table) were removed in favor of
creative agent-based format discovery per AdCP v2.4.
"""

import json
import logging
from collections.abc import Iterable, Mapping
from fnmatch import fnmatch
from typing import Any

from adcp.canonical_formats import CANONICAL_CREATIVE_AGENT_URL, format_is_supported, load_default_registry
from adcp.types.domains.core.format_id import FormatReferenceStructuredObject as LibraryFormatId
from adcp.types.domains.registries.v1_canonical_mapping import V1Pattern as LibraryV1GlobPattern
from pydantic import ValidationError

from src.core.database.database_session import get_db_session
from src.core.errors.details import EntityRefDetails
from src.core.exceptions import AdCPFormatNotFoundError, AdCPSalesAgentError
from src.core.schemas import (
    CreativeFormatIdentity,
    Format,
    FormatKey,
    FormatOptionIdentity,
    LibraryCreativeAsset,
    creative_format_identity,
    format_id_identity,
    format_key_parts,
)
from src.core.security.outbound_http import UrlProvenance
from src.core.validation_helpers import run_async_in_sync_context

# What callers may hand the identity helpers: a structured reference, a bare
# dict off the wire, or a legacy string id.
FormatRef = str | LibraryFormatId | Mapping[str, Any]


logger = logging.getLogger(__name__)


# ── Format identity and kind: asked here, never re-decided at a call site ─────
#
# Two format references name the same format when they share a federation
# identity — the ``(canonical agent_url, id)`` pair ``format_id_identity``
# computes. Call sites used to compare with ``==`` on the model, which is
# Pydantic's STRUCTURAL equality — same fields AND same class. That works only
# while every producer happens to build the same concrete class, an invariant
# nothing declared and one transport quietly broke: the local ``FormatId``
# subclass (schemas/_base.py, four convenience methods, zero extra fields) never
# compares equal to the library value every other producer makes, so a lookup
# keyed on ``==`` missed on A2A and the whole agent-dial branch was skipped in
# silence.
#
# Identity is (agent_url, id) per the pinned core/format-id.json, and
# ``src.core.schemas.format_id_identity`` is the ONE implementation of it in
# this codebase — including the spec-mandated canonicalization of agent_url,
# which it delegates to the SDK. Nothing here re-implements that; these are
# thin, named delegations so there is ONE answer to "same format?" instead of
# one per call site. A second rule (the SDK's own ``formats_are_equivalent``,
# which additionally legacy-upgrades ``display_300x250`` into a parameterized
# canonical id) would answer differently for the same pair of references — so
# equivalence is asked of ``format_id_identity`` and of nothing else.
# Directional SUPPORT is a different question, and that one is still the SDK's
# (see :func:`format_accepted_by`).


def format_ref_id(ref: FormatRef) -> str | None:
    """The bare ``id`` of a format reference, whatever shape it arrives in.

    A ``format_id`` reaches this module as a structured model, as a wire dict,
    or as a legacy bare string, depending on which producer built it — so
    reaching for ``.id`` works only until it does not. Asking here keeps that
    fact in ONE place instead of at each call site, which is the same mistake
    the ``==`` comparisons made about class identity.
    """
    if isinstance(ref, str):
        return ref
    if isinstance(ref, Mapping):
        value = ref.get("id")
        return str(value) if value is not None else None
    value = getattr(ref, "id", None)
    return str(value) if value is not None else None


def format_identity(ref: FormatRef) -> FormatKey:
    """The federation identity of a format reference, in any shape it arrives in.

    Delegates the rule itself to ``src.core.schemas.format_id_identity`` — the
    single place allowed to decide what "the same format" means — and adds only
    the shape normalization: a wire dict is validated into the library model, and
    a bare id is namespaced to the canonical creative agent (the same default the
    SDK applies when a reference omits ``agent_url``).

    That default is why this is the WRONG helper for an unscoped "search every
    agent for this id" lookup: namespacing a bare string silently narrows the
    search to the reference agent. Match on :func:`format_ref_id` there instead —
    ``get_format``'s no-``agent_url`` branch does exactly that.
    """
    if isinstance(ref, str):
        ref = LibraryFormatId.model_validate({"agent_url": CANONICAL_CREATIVE_AGENT_URL, "id": ref})
    elif isinstance(ref, Mapping):
        ref = LibraryFormatId.model_validate({"agent_url": CANONICAL_CREATIVE_AGENT_URL, **ref})
    return format_id_identity(ref)


def canonical_kind_for(ref: FormatRef, *, spec: Format | None = None) -> str:
    """The canonical ``format_kind`` a deprecated ``format_id`` projects to.

    THE ONE direction that resolves. ``registries/v1-canonical-mapping.json`` is
    "authoritative for v1 -> v2 projection only", and the reverse is forbidden outright:
    a seller MUST NOT synthesize a v1 ``format_id`` by inverting a structural match,
    because the registry's id slugs carry no ``agent_url`` half and a glob entry has no
    single literal to invert to. That asymmetry is why the canonical kind -- not the
    legacy reference -- is the identity everything inside this seller shares.

    Two of the normative six steps are implementable from what a seller holds today, and
    they are tried in the spec's order:

    1. **The agent's own projection.** ``core/format-id.json`` lets a format declare its
       canonical projection, and ``CanonicalProjectionReference.kind`` is required when it
       does. An explicit declaration outranks any inference, so it is consulted first.
    2. **The registry glob.** 45 mappings carry a ``v1_pattern.format_id_glob`` and a
       ``v2.canonical``; measured, all 7 distinct targets are members of the pinned
       vocabulary, so a match yields a usable kind without further checking.

    The remaining steps -- structural match and ambiguous-family -- need the format's
    declared structure rather than its id, and a seller-published
    ``v1_format_ref[]`` needs ``Product.format_options[]``, which this seller does not
    carry yet. Until those exist this fails CLOSED, which is the sixth step and the only
    safe end to the order: a kind guessed from an unmatched id would be a fabricated
    identity, and every comparison downstream keys on it.

    Args:
        ref: the deprecated reference, in any shape :func:`format_identity` accepts.
        spec: the fetched format declaration, when the caller already has it. Passing it
            is what makes step 1 reachable; without it only the registry is consulted.

    Returns:
        A ``format_kind`` from the pinned vocabulary.

    Raises:
        ValueError: when neither step resolves. The caller decides how to refuse -- this
            module does not mint an error code for a projection it could not make.
    """
    declared = getattr(spec, "canonical", None) if spec is not None else None
    if declared is not None:
        kind = getattr(declared, "kind", None)
        if kind is not None:
            return str(kind)

    legacy_id = format_ref_id(ref)
    if legacy_id is not None:
        for mapping in load_default_registry().mappings:
            # The registry's ``v1_pattern`` is a closed two-arm union, and the arms ARE the
            # two normative steps: ``format_id_glob`` is step 3 (38 of the 45 mappings),
            # ``structural`` is step 4 (the other 7). Discriminated by type rather than by
            # ``getattr``, so the untried arm is a visible skip instead of a silent miss --
            # a structural entry needs the format's declared shape, which this does not have.
            pattern = mapping.v1_pattern
            if isinstance(pattern, LibraryV1GlobPattern) and fnmatch(legacy_id, pattern.format_id_glob):
                return str(mapping.v2.canonical)

    raise ValueError(
        f"no canonical projection for legacy format_id {legacy_id!r}: the agent declares none "
        "and no registry pattern matches"
    )


def creative_identity_of(creative: LibraryCreativeAsset, *, spec: Format | None = None) -> CreativeFormatIdentity:
    """A creative's format identity, with a legacy reference PROJECTED to its canonical kind.

    THE ONE edge where the two identities meet. ``creative_format_identity`` reads whichever
    arm the creative carries; this wraps it with the only direction that resolves, so every
    layer past here keys on ``identity.kind`` instead of branching on which arm arrived.

    A projection that does not resolve leaves ``kind`` as ``None`` and is NOT a refusal. The
    sixth normative step is to fail closed, and failing closed here means "this reference has
    no canonical kind", not "this creative is invalid": ``core/creative-asset.json`` keeps
    ``format_id`` as a supported branch through 4.x, so refusing a legacy creative whose id
    no registry pattern matches would refuse spec-legal traffic. The retained assertion is
    then the only identity the creative has, which is exactly what the one-way rule leaves a
    seller holding.

    Args:
        creative: the pinned sync input, or this repo's DTO subclass of it. Typed rather than
            duck-read: both declare the two arms, so ``format_id`` is a plain attribute and
            mypy holds every caller to a real model instead of to whatever answers.
        spec: the fetched format declaration, when the caller already has it. Passing it is
            what makes the agent's own explicit projection (step 1) reachable; without it
            only the registry glob (step 3) is consulted.
    """
    kind: str | None = None
    format_id = creative.format_id
    if format_id is not None:
        try:
            kind = canonical_kind_for(format_id, spec=spec)
        except ValueError:
            logger.debug("No canonical projection for %r; the retained assertion is its only identity", format_id)
    return creative_format_identity(creative, kind=kind)


def same_format(left: FormatRef, right: FormatRef) -> bool:
    """Whether two format references name the same format.

    Deliberately NOT ``==``: that compares Python classes as well as values.
    Deliberately not a hand-rolled string compare either — the pinned schema
    makes canonicalizing ``agent_url`` before treating two references as one a
    MUST, and :func:`format_identity` is where that happens.
    """
    return format_identity(left) == format_identity(right)


def format_identity_or_none(entry: Any) -> FormatKey | None:
    """The federation identity of a format reference, or None if it is not one.

    Two things separate this from :func:`format_identity`. It absorbs the ONE
    shape variance a persisted reference has — ``Product.format_ids`` is
    ``list[FormatId]`` in the schema but a JSON ``list[dict]`` in the column,
    and rows predating the AdCP v3.1 rename key the id as ``format_id`` rather
    than ``id`` — and it answers ``None`` instead of raising when the value is
    not a usable reference at all. A ``None`` field is read as ABSENT, so a
    reference carrying ``agent_url: None`` takes the same canonical-agent
    default a reference omitting the key does.

    ``None`` is the right answer here because both callers act on it correctly
    without a second code path: a product entry that yields None declares no
    restriction, and a creative that yields None matches no product entry,
    which is exactly "this format is not one the product accepts". Raising
    would turn one corrupt row into a 500 on a buyer's request.

    Asking here is what lets a call site pose the identity question instead of
    re-deciding what "the same agent_url" means. The three sites that check a
    creative against its product each grew a private ``normalize_url`` doing a
    bare ``rstrip("/")`` and, in two of them, an unmandated
    ``removesuffix("/mcp")`` that collapsed one host's MCP and A2A endpoints
    into a single agent. The pinned ``core/format-id.json`` requires the AdCP
    canonical form before two references may be treated as the same, and
    :func:`format_identity` is the one place that applies it.
    """
    # The absent-field and legacy-key handling applies to the persisted dict
    # shape only. A model already carries a validated ``agent_url`` and ``id`` (both
    # required on the library type), so it is handed on as the model it is and never
    # dumped here — business logic does not serialize a model to inspect it.
    try:
        ref: Any = entry
        if isinstance(ref, Mapping):
            ref = {k: v for k, v in ref.items() if v is not None}
            if "id" not in ref and "format_id" in ref:
                ref["id"] = ref["format_id"]
            ref.pop("format_id", None)
            if "id" not in ref:
                return None
        return format_identity(ref)
    except (ValidationError, ValueError, TypeError, AttributeError):
        logger.warning("Unusable stored format reference, ignored: %r", entry)
        return None


def product_format_identities(format_ids: Iterable[Any] | None) -> set[FormatKey]:
    """The federation identities a product's declared ``format_ids`` accept.

    Empty means the product imposes no format restriction — the same reading
    an empty column has, and the reading every caller already applied.
    """
    identities = (format_identity_or_none(entry) for entry in format_ids or [])
    return {identity for identity in identities if identity is not None}


def product_format_kinds(format_options: Iterable[Any] | None) -> set[str]:
    """The canonical format kinds a product's declared ``format_options`` accept.

    The CANONICAL half of the question :func:`product_format_identities` asks of the
    legacy half, and placed beside it so the two halves of one filter question stay
    together rather than one living in whichever tool first needed it.

    Empty means the product declares no canonical kind. That reading differs from the
    legacy half's deliberately: ``product_format_identities`` treats empty as "imposes
    no format restriction", because a product with no ``format_ids`` used to mean a
    product that had not narrowed itself. A product with no ``format_options`` has not
    declared a KIND, and ``core/product-filters.json`` asks for "products accepting any
    of these canonical format kinds" -- a product declaring none accepts none of them,
    so it is not selected. Reading empty as "matches everything" here is precisely the
    bug ``standard_formats_only`` had: an absent arm silently satisfied every filter.

    ``str()`` on the kind because it arrives as a ``StrEnum`` member on the model and as
    a plain string in a filter. The two compare equal today because the generated type
    is a ``StrEnum``; normalizing both sides means that stays true if it ever is not.
    """
    return {str(declaration.format_kind) for declaration in format_options or []}


def product_format_option_identities(format_options: Iterable[Any] | None) -> set[FormatOptionIdentity]:
    """The format-option identities a product's declarations name.

    The third reader beside :func:`product_format_identities` (legacy arm) and
    :func:`product_format_kinds` (canonical kind), and the finest-grained of them:
    ``core/product-filters.json`` asks ``format_option_refs`` for products accepting "any of
    these EXACT publisher- or product-scoped canonical format options", so the comparison is
    whole identities and never their parts.

    :class:`FormatOptionIdentity` already owns the scope distinction, and owns it the way the
    pin defines it: the two arms of ``core/format-option-ref.json`` make ``publisher_domain``
    required on one and forbidden on the other, so the domain's PRESENCE is the discriminator
    and a publisher-catalog option and a product-local option sharing one
    ``format_option_id`` are DIFFERENT options. Constructed directly here rather than through
    ``of_reference`` because a declaration carries no ``scope`` member to read -- the
    declaration schema's own allOf says ``publisher_domain`` "is addressable only alongside
    ``format_option_id``" -- so presence is the only signal there is, which is what that
    identity derives its scope from anyway.

    A declaration naming NO option is skipped rather than given an empty identity. A bare
    canonical declaration (``format_kind`` + ``params``, no option id) narrows a kind without
    naming a catalogued option, so it accepts none of the refs this filter can name.
    """
    identities: set[FormatOptionIdentity] = set()
    for declaration in format_options or []:
        option_id = declaration.format_option_id
        if not option_id:
            continue
        identities.add(
            FormatOptionIdentity(
                publisher_domain=declaration.publisher_domain,
                format_option_id=option_id,
            )
        )
    return identities


def format_display(identity: FormatKey) -> str:
    """``<canonical agent_url>/<id>`` — how a format identity is spelled to a buyer.

    The identity, not the raw reference: an error that lists "supported
    formats" spelled differently from the values actually compared reads as a
    contradiction to whoever has to act on it.

    The single-slash join is DISPLAY ONLY and never a comparison. A canonical
    agent_url whose path is empty ends in ``/`` (the algorithm's step 5), so a
    naive ``f"{url}/{id}"`` renders ``https://x.org//display_300x250`` for the
    common case. Collapsing that pair of slashes makes two identities that
    differ ONLY by a trailing slash on a non-empty path (``/a`` vs ``/a/``,
    which the spec keeps distinct) render alike; that is accepted here because
    this string is read by a human deciding what to resubmit, and nothing
    parses it back.

    THE ONE reader of a key's halves (via ``format_key_parts``), and it is a renderer:
    splitting a key anywhere else is how ``id``-alone matching gets reintroduced.
    """
    agent_url, format_id = format_key_parts(identity)
    separator = "" if agent_url.endswith("/") else "/"
    return f"{agent_url}{separator}{format_id}"


def format_accepted_by(requested: FormatRef, supported: FormatRef) -> bool:
    """Whether *supported* satisfies a request for *requested*.

    Distinct from :func:`same_format`: support is directional (a parameterized
    supported format can satisfy a narrower request), which is why the SDK gives
    it its own predicate rather than reusing equivalence — and why this one
    delegates to ``adcp.canonical_formats.format_is_supported`` rather than to
    the identity pair, which cannot express direction. The SDK predicate reads
    attributes, so a local ``FormatId`` subclass is handed over as is.
    """
    return format_is_supported(requested, supported)


def find_format(formats: Iterable[Format], format_id: FormatRef) -> Format | None:
    """The format in *formats* that *format_id* names, or None.

    ONE definition of "is this the format the buyer asked for", so no caller can
    reintroduce a class-sensitive ``==`` against a registry listing. ``FormatId``
    exists twice -- the library type the AdCP schemas declare and our subclass --
    and pydantic v2 equality is class-sensitive, so comparing the models matched
    NOTHING whenever the two sides were built by different code paths
    (the A2A boundary built one, MCP and REST the other; #2093).

    Identity is ``format_id_identity``'s ``(canonical agent_url, id)``, the pair the
    graded contract matches on (``core/format-id.json`` requires ``[agent_url, id]``;
    the list_formats storyboard step uses ``match_keys: [agent_url, id]``) and the
    same pair ``list_creative_formats`` filters with. Notably that means a
    PARAMETERIZED reference resolves to the template it parameterizes -- which is
    the point of a template format, and what lets a 300x250 request find the
    ``display`` format's spec.

    PURE: no HTTP and no DB, so it is callable from inside a savepoint where
    ``get_format`` is not — the creative-sync paths pre-fetch their catalog
    outside the transaction for exactly that reason and then need to select from
    it without dialling anything.
    """
    wanted = format_identity(format_id)
    return next((fmt for fmt in formats if format_identity(fmt.format_id) == wanted), None)


def is_agent_backed(fmt: Format) -> bool:
    """Whether this format is served by a creative agent.

    Asks the format, rather than probing it: ``fmt.agent_url`` is a declared
    property on the local Format (schemas/_base.py), not an attribute that may
    or may not be there. Compose with — do not duplicate —
    :func:`is_dialled_agent_url`: an adapter pseudo-URL is agent-backed but
    never dialled.
    """
    return fmt.agent_url is not None


def is_generative(fmt: Format) -> bool:
    """Whether this format is built by the agent rather than supplied whole.

    ``output_format_ids`` IS a declared field on ``adcp.types.Format``, so the
    ``getattr(fmt, "output_format_ids", None)`` guard call sites used protected
    against nothing while the sibling read of ``agent_url`` — the one that could
    actually surprise — went undefended.
    """
    return bool(fmt.output_format_ids)


def is_dialled_agent_url(agent_url: str) -> bool:
    """Whether *agent_url* names an endpoint we will actually dial over HTTP.

    False for an adapter-provided pseudo-URL like ``broadstreet://<tenant_id>``
    (advertised by ``creative_formats.py`` and the Broadstreet adapter): those
    formats are served by the adapter in-process, so there is no request to
    make, no address to judge, and an egress gate applied to one would refuse
    a format the SELLER published to the buyer.

    Shared by every format-fetch call site (``creatives/_validation.py``'s
    ingest gate, ``media_buy_create.py``'s pre-adapter validation and asset
    build) so the adapter-format exemption is decided once, here, rather than
    re-derived per call site.
    """
    return agent_url.startswith(("http://", "https://"))


def fetch_format_spec(agent_url: str, format_id: str, *, provenance: UrlProvenance | None = None) -> Format | None:
    """Fetch one format spec from the creative-agent registry (sync bridge).

    THE single fetch path for format specs — create_media_buy,
    sync_creatives validation, and get_format all route through here so typed
    transient errors behave identically on every tool:

    - Typed ``AdCPSalesAgentError`` from the registry (429 -> AdCPRateLimitError,
      5xx/timeout/connect -> AdCPServiceUnavailableError) PROPAGATES: it carries
      its own recovery semantics, and swallowing it into ``None`` degrades a
      transient agent failure to a terminal "unknown format" rejection.
    - ``None`` means the agent genuinely doesn't expose the format (unknown-
      format semantics — the caller decides how to reject or fall back).
    - Untyped exceptions are logged and become ``None``: the registry types all
      its network errors, so an untyped one here is a programming surprise, not
      a transport signal.

    ``provenance`` passes straight through to the registry — a
    :class:`CounterpartyUrl` when a buyer's request document supplied
    ``agent_url``, optionally naming the request path; ``None`` for an
    operator-registered agent.
    """
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()
    try:
        return run_async_in_sync_context(registry.get_format(agent_url, format_id, provenance=provenance))
    except AdCPSalesAgentError:
        raise
    except Exception as e:
        logger.warning(f"Could not fetch format {format_id} from {agent_url}: {e}")
        return None


def get_format(
    format_id: str,
    agent_url: str | None = None,
    tenant_id: str | None = None,
    product_id: str | None = None,
    *,
    provenance: UrlProvenance | None = None,
) -> Format:
    """Resolve format with priority: product override → creative agent discovery.

    Args:
        format_id: Format identifier (e.g., "display_300x250_image")
        agent_url: Optional creative agent URL (defaults to AdCP standard agent)
        tenant_id: Optional tenant ID for agent lookup
        product_id: Optional product ID for product-level overrides
        provenance: Whose URL ``agent_url`` is, forwarded to
            :func:`fetch_format_spec` unchanged. A caller re-dialling a
            buyer-supplied URL it already fetched once (e.g. a fallback path)
            MUST pass the same ``CounterpartyUrl`` it used the first time —
            omitting it silently reclassifies the same URL as operator
            configuration and routes it off the egress seam entirely.

    Returns:
        Format object with all configuration

    Raises:
        AdCPFormatNotFoundError: If format_id not found in any source
    """
    # Check product override first
    if product_id and tenant_id:
        override = _get_product_format_override(tenant_id, product_id, format_id, agent_url=agent_url)
        if override:
            return override

    # Get from creative agent registry
    from src.core.creative_agent_registry import get_creative_agent_registry

    registry = get_creative_agent_registry()

    # If agent_url provided, get format directly from that agent
    # Coerce to str: FormatId.agent_url is Pydantic AnyUrl (not a str subclass)
    if agent_url:
        fmt = fetch_format_spec(str(agent_url), format_id, provenance=provenance)
        if fmt:
            return fmt
    else:
        # Search all agents for this format. The caller supplied NO agent scope,
        # so the match is on the id alone — matching on full (agent_url, id)
        # identity here would silently narrow "any agent" to "the reference
        # agent", because upgrading a bare string defaults agent_url to the
        # canonical creative agent.
        #
        # This branch was dead before: it compared ``fmt.format_id`` (a FormatId
        # MODEL) against ``format_id`` (a str), which is never equal — so the
        # one canonical resolver's fallback always fell through to the raise.
        all_formats = run_async_in_sync_context(registry.list_all_formats(tenant_id=tenant_id))
        # The id component alone, read through ``format_ref_id``: the same
        # component comparison ``CreativeAgentRegistry.get_format`` makes, and the
        # only one available when this parameter is a bare ``str`` (#2093). An id
        # with no agent_url to namespace it is inherently ambiguous across agents;
        # first in listing order wins, which is what "search all agents" has
        # always meant here.
        for fmt in all_formats:
            if format_ref_id(fmt.format_id) == format_id:
                return fmt

    # Not found anywhere. The identifiers travel as structured detail rather than
    # interpolated prose: the buyer needs to know WHICH format_id was rejected, and
    # ``details`` is where a machine can read it.
    raise AdCPFormatNotFoundError(
        field="format_id",
        # The conditional spreads this replaces kept absent identifiers out of the
        # block; ``to_wire()`` drops unset fields, so a plain None says the same
        # thing without three dict literals.
        details=EntityRefDetails(format_id=format_id, agent_url=agent_url, tenant_id=tenant_id),
    )


def _get_product_format_override(
    tenant_id: str, product_id: str, format_id: str, agent_url: str | None = None
) -> Format | None:
    """Get product-level format override from product.implementation_config.

    Product can override any format's platform_config. Example:
    {
        "format_overrides": {
            "display_300x250": {
                "platform_config": {
                    "gam": {
                        "creative_placeholder": {
                            "width": 1,
                            "height": 1,
                            "creative_template_id": 12345678
                        }
                    }
                }
            }
        }
    }

    Args:
        tenant_id: Tenant identifier
        product_id: Product identifier
        format_id: Format to look up
        agent_url: Optional creative agent URL (needed to fetch base format)

    Returns:
        Format with overridden config, or None if no override exists
    """
    from sqlalchemy import text

    with get_db_session() as session:
        result = session.execute(
            text(
                "SELECT implementation_config FROM products WHERE tenant_id = :tenant_id AND product_id = :product_id"
            ),
            {"tenant_id": tenant_id, "product_id": product_id},
        )
        row = result.fetchone()
        if not row or not row[0]:
            return None

        # Parse implementation_config JSON
        impl_config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        format_overrides = impl_config.get("format_overrides", {})

        if format_id not in format_overrides:
            return None

        # Get base format from creative agent registry (WITHOUT product_id to avoid recursion)
        from src.core.creative_agent_registry import get_creative_agent_registry

        registry = get_creative_agent_registry()

        try:
            # format_id is a string key in format_overrides dict
            # Pass agent_url to find the base format from the correct creative agent
            base_format = get_format(format_id, agent_url=agent_url, tenant_id=tenant_id, product_id=None)
        except AdCPFormatNotFoundError:
            # The base format genuinely does not exist, so there is nothing to
            # override. The only condition this branch was ever meant to handle.
            return None
        except AdCPSalesAgentError:
            # Anything else typed -- a rate limit, an unreachable agent -- is NOT
            # "no such format". Swallowing it here reported a transient outage as
            # an absent override, which is a lie the buyer cannot act on.
            raise

        # Apply override to base format
        override_config = format_overrides[format_id]

        # Merge platform_config override
        if "platform_config" in override_config:
            # Access platform_config directly from the model, not via model_dump(),
            # because platform_config has exclude=True and model_dump() drops it.
            base_platform_config = base_format.platform_config or {}
            override_platform_config = override_config["platform_config"]

            # Deep merge platform configs (override takes precedence)
            merged_platform_config = {**base_platform_config}
            for platform, config in override_platform_config.items():
                if platform in merged_platform_config:
                    # Merge platform-specific configs
                    merged_platform_config[platform] = {
                        **merged_platform_config[platform],
                        **config,
                    }
                else:
                    merged_platform_config[platform] = config

            return base_format.model_copy(update={"platform_config": merged_platform_config})

        return base_format


def list_available_formats(
    tenant_id: str | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    is_responsive: bool | None = None,
    asset_types: list[str] | None = None,
    name_search: str | None = None,
) -> list[Format]:
    """List all formats available to a tenant from all registered creative agents.

    Args:
        tenant_id: Optional tenant ID to include tenant-specific agents
        max_width: Maximum width in pixels (inclusive)
        max_height: Maximum height in pixels (inclusive)
        min_width: Minimum width in pixels (inclusive)
        min_height: Minimum height in pixels (inclusive)
        is_responsive: Filter for responsive formats
        asset_types: Filter by asset types
        name_search: Search by name

    Returns:
        List of all available Format objects from all registered agents
    """
    import logging

    logger = logging.getLogger(__name__)

    from src.core.creative_agent_registry import get_creative_agent_registry

    logger.info(f"[list_available_formats] Starting format fetch for tenant_id={tenant_id}")

    try:
        registry = get_creative_agent_registry()
    except Exception as e:
        logger.error(f"[list_available_formats] Failed to get creative agent registry: {e}", exc_info=True)
        return []

    # Get formats from all agents (default + tenant-specific)
    try:
        formats = run_async_in_sync_context(
            registry.list_all_formats(
                tenant_id=tenant_id,
                max_width=max_width,
                max_height=max_height,
                min_width=min_width,
                min_height=min_height,
                is_responsive=is_responsive,
                asset_types=asset_types,
                name_search=name_search,
            )
        )
    except Exception as e:
        # Deliberately still degrades to [] for EVERY failure, typed or not. The
        # only caller is the admin UI (src/admin/blueprints/products.py:156), which
        # catches the SDK's adcp.exceptions.ADCPError -- a different class tree from
        # src.core.exceptions.AdCPSalesAgentError -- so propagating a typed error here does not
        # reach a buyer, it 500s an admin page that used to degrade. salesagent-w4x1's
        # defect ("buyer sees empty catalog SUCCESS on an agent 429") is real but is
        # NOT at this site; wiring this path to a buyer is what would create it.
        logger.error(f"[list_available_formats] Error fetching formats: {e}", exc_info=True)
        return []

    logger.info(f"[list_available_formats] Successfully fetched {len(formats)} formats")
    return formats
