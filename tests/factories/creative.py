"""Factory-boy factories for Creative and CreativeAssignment ORM models."""

from __future__ import annotations

from types import SimpleNamespace

import factory
from factory.alchemy import SQLAlchemyModelFactory

from src.core.database.models import Creative, CreativeAssignment
from src.core.database.repositories.creative import _identity_columns
from src.core.format_resolver import creative_identity_of
from src.core.schemas import CreativeFormatIdentity, FormatId

from .core import TenantFactory
from .creative_asset import build_assets, image_spec
from .media_buy import MediaBuyFactory
from .principal import PrincipalFactory

#: The creative agent a factory-built creative asserts a format from, unless a test names
#: another one.
DEFAULT_CREATIVE_AGENT_URL = "https://creative.adcontextprotocol.org"


def _seeded_identity(obj) -> CreativeFormatIdentity:
    """The format identity a factory-built row carries, through the PRODUCTION builder.

    A test says which arm the creative carries -- a legacy reference via ``agent_url`` +
    ``format``, or a canonical kind via ``canonical_kind`` -- and the four stored columns are
    derived from that by the same code the sync path runs, including the v1 -> v2 projection.
    So a factory row and a synced row cannot differ in shape, which is what a factory seeding
    the columns by hand could not promise: the identity used to be three partial columns and
    the factory set two of them.
    """
    if obj.canonical_kind is not None:
        return CreativeFormatIdentity(kind=obj.canonical_kind)
    reference = FormatId(agent_url=obj.agent_url, id=obj.format)
    return creative_identity_of(SimpleNamespace(format_id=reference, format_kind=None))


def stamp_format_identity(
    row,
    *,
    format_id: str = "display_300x250",
    agent_url: str = DEFAULT_CREATIVE_AGENT_URL,
    canonical_kind: str | None = None,
) -> CreativeFormatIdentity:
    """Stamp the four stored identity columns onto a MOCK creative row, and return them.

    A ``MagicMock`` answers a fresh ``Mock`` for any attribute nobody stubbed, and a ``Mock``
    is not a state any of these columns can hold: ``CreativeFormatIdentity.from_row``
    validates ``legacy_format_id`` as the JSON document the column holds, so an unstubbed row
    fails inside the reader rather than in the code under test. The columns are derived here
    through the same production mapping ``CreativeRepository.create`` uses, so a mock row and
    a real row agree -- and a column added to the identity is stamped in ONE place instead of
    at every mock.

    For a row that goes through the real session, use ``CreativeFactory`` instead.
    """
    identity = _seeded_identity(SimpleNamespace(canonical_kind=canonical_kind, agent_url=agent_url, format=format_id))
    for column, value in _identity_columns(identity).items():
        setattr(row, column, value)
    return identity


class CreativeFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Creative
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"
        # The identity knobs are inputs, not columns: `_seeded_identity` turns them into the
        # four columns that exist.
        exclude = ("principal", "agent_url", "format", "canonical_kind", "identity")

    # Composite PK fields
    creative_id = factory.Sequence(lambda n: f"creative_{n:04d}")
    tenant = factory.SubFactory(TenantFactory)
    tenant_id = factory.LazyAttribute(lambda o: o.tenant.tenant_id)
    principal = factory.SubFactory(PrincipalFactory, tenant=factory.SelfAttribute("..tenant"))
    principal_id = factory.LazyAttribute(lambda o: o.principal.principal_id)

    # Required fields
    name = factory.LazyAttribute(lambda o: f"Test Creative {o.creative_id}")

    # --- Format identity: knobs in, four columns out ---
    # `agent_url` + `format` name the legacy reference a creative asserts (the default, and
    # what most scenarios exercise); `canonical_kind` instead builds a creative identified
    # by its canonical kind, which asserts no reference at all.
    agent_url = DEFAULT_CREATIVE_AGENT_URL
    format = "display_300x250"
    canonical_kind = None
    identity = factory.LazyAttribute(_seeded_identity)
    # Each column read off the ONE production mapping by its own name, so a column added to
    # the identity is a line here and nothing else -- never a second copy of the mapping.
    format_kind = factory.LazyAttribute(lambda o: _identity_columns(o.identity)["format_kind"])
    format_option_ref = factory.LazyAttribute(lambda o: _identity_columns(o.identity)["format_option_ref"])
    legacy_format_id = factory.LazyAttribute(lambda o: _identity_columns(o.identity)["legacy_format_id"])
    legacy_format_key = factory.LazyAttribute(lambda o: _identity_columns(o.identity)["legacy_format_key"])

    # Mirrors the production default. Must stay an AdCP CreativeStatus member: a non-spec
    # value (this was "pending") made every factory-built creative reach list_creatives
    # through the reader's unparseable-status branch rather than through real status
    # semantics.
    status = "pending_review"
    data = factory.LazyFunction(lambda: {"assets": build_assets(image_spec("banner"))})

    class Params:
        """Traits for common creative configurations."""

        approved = factory.Trait(status="approved")


class CreativeAssignmentFactory(SQLAlchemyModelFactory):
    class Meta:
        model = CreativeAssignment
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "commit"
        exclude = ("creative", "media_buy")

    assignment_id = factory.Sequence(lambda n: f"assignment_{n:04d}")
    creative = factory.SubFactory(CreativeFactory)
    tenant_id = factory.LazyAttribute(lambda o: o.creative.tenant_id)
    creative_id = factory.LazyAttribute(lambda o: o.creative.creative_id)
    principal_id = factory.LazyAttribute(lambda o: o.creative.principal_id)
    media_buy = factory.SubFactory(MediaBuyFactory, tenant=factory.SelfAttribute("..creative.tenant"))
    media_buy_id = factory.LazyAttribute(lambda o: o.media_buy.media_buy_id)
    package_id = factory.Sequence(lambda n: f"pkg_{n:04d}")
    weight = 100
