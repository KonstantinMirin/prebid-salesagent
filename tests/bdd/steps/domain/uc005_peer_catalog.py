"""UC-005: a creative agent's catalog is parsed entry by entry, and a discard is reported.

Scenarios ``T-UC-005-peer-catalog-partial-discard``, ``-empty`` and ``-all-discarded``
(#1333). The Givens hand ``CreativeFormatsEnv.set_peer_format_payload`` the agent's
``formats`` array as RAW JSON, because the obligation is about what the seller does with
a document it did not write: in process the env serves it from a real MCP endpoint and
production's own registry dials it, and over e2e_rest the compose stack's capture service
serves it to the live server. Either way the seller's parse is the one under test.

The Thens read the wire. The agent's formats are located by the ``agent_url`` the agent
published inside each ``format_id``, so the reference catalog the default agent answers
with never stands in for them.

@source repo=adcp ref=v3.2.7 path=static/schemas/source/media-buy/list-creative-formats-response.json pointer=/properties/errors
"""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, then

from src.core.schemas import canonical_agent_url
from tests.bdd.steps._outcome_helpers import wire_advisory_errors, wire_field

#: The identity the agent publishes on its formats. It is not where the agent is
#: dialled -- the env decides that -- which is what lets one value serve both worlds.
PEER_AGENT_URL = "https://peer-creatives.example"


def _peer_entry(format_id: str, **fields: Any) -> dict[str, Any]:
    """One entry of the agent's catalog, exactly as the agent sends it."""
    return {"format_id": {"agent_url": PEER_AGENT_URL, "id": format_id}, **fields}


#: Conforming, with members this pin's enums do not model in two closed-enum lists. Its
#: name sorts ahead of every reference-catalog name, so the default page carries it.
_CONFORMING = _peer_entry(
    "acme_peer_banner",
    name="Acme Peer Banner",
    accepts_parameters=["future_parameter"],
    reported_metrics=["impressions", "future_metric"],
)
#: ``name`` is required by core/format.json.
_MISSING_NAME = _peer_entry("acme_peer_unnamed")
#: A non-string member is a type error, not an unknown enum value, so it is not tolerated.
_NON_STRING_PARAMETER = _peer_entry("acme_peer_numeric", name="Acme Peer Numeric", accepts_parameters=[42])


@given("a creative agent whose catalog includes one entry the pinned schema cannot validate")
def given_peer_catalog_with_one_invalid_entry(ctx: dict) -> None:
    ctx["env"].set_peer_format_payload([_CONFORMING, _MISSING_NAME])


@given("a creative agent whose catalog has only entries the pinned schema cannot validate")
def given_peer_catalog_all_invalid(ctx: dict) -> None:
    ctx["env"].set_peer_format_payload([_MISSING_NAME, _NON_STRING_PARAMETER])


@given("a creative agent whose catalog has no entries")
def given_peer_catalog_empty(ctx: dict) -> None:
    ctx["env"].set_peer_format_payload([])


def _peer_formats(ctx: dict) -> list[dict[str, Any]]:
    """The formats on the wire that the agent published, by the agent_url in their format_id."""
    formats = wire_field(ctx, "formats")
    assert isinstance(formats, list), f"formats is not a JSON array on the wire: {formats!r}"
    peer = canonical_agent_url(PEER_AGENT_URL)
    return [f for f in formats if canonical_agent_url(f["format_id"]["agent_url"]) == peer]


def _peer_format_ids(ctx: dict) -> list[str]:
    return [f["format_id"]["id"] for f in _peer_formats(ctx)]


@then(parsers.parse('only the creative agent\'s format "{format_id}" should be returned'))
def then_only_peer_format_returned(ctx: dict, format_id: str) -> None:
    returned = _peer_format_ids(ctx)
    assert returned == [format_id], f"expected exactly the agent's format {format_id!r}, got {returned}"


@then("no formats from the creative agent should be returned")
def then_no_peer_formats_returned(ctx: dict) -> None:
    returned = _peer_format_ids(ctx)
    assert returned == [], f"expected no formats from the agent, got {returned}"


@then(parsers.parse('the creative agent\'s format should carry {field} "{values}"'))
def then_peer_format_carries(ctx: dict, field: str, values: str) -> None:
    """The list arrives exactly as the agent sent it, members the pin does not model included."""
    (entry,) = _peer_formats(ctx)
    expected = values.split(", ")
    assert entry.get(field) == expected, f"{field}: expected {expected}, got {entry.get(field)!r}"


@then(parsers.parse('the discarded entries should be reported as "{code}" on "{section}" with recovery "{recovery}"'))
def then_discard_reported(ctx: dict, code: str, section: str, recovery: str) -> None:
    """Exactly one advisory, however many entries were discarded: it names the agent's loss."""
    reported = [{key: error.get(key) for key in ("code", "field", "recovery")} for error in wire_advisory_errors(ctx)]
    assert reported == [{"code": code, "field": section, "recovery": recovery}], (
        f"expected one {code} advisory on {section!r}, got {reported}"
    )
