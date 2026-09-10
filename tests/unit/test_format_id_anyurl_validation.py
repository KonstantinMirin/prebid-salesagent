"""Format identity over FormatId objects whose ``agent_url`` is a pydantic ``AnyUrl``.

Regression origin: ``.rstrip()`` was called directly on ``AnyUrl`` during
create_media_buy's format validation and raised ``AttributeError``. These tests
used to guard that by RE-IMPLEMENTING the normalization inline and asserting the
re-implementation worked — which graded nothing in ``src/``. They now drive the
real entry point, ``format_resolver.format_identity_or_none``, which is the one
place that turns a reference of any shape into a comparison key.
"""

from pydantic import AnyUrl

from src.core.format_resolver import format_display, format_identity_or_none
from src.core.schemas import FormatId

AGENT = "https://creative.adcontextprotocol.org"


def test_anyurl_agent_url_does_not_raise_and_ignores_a_trailing_slash():
    """A trailing slash is not part of the identity, and AnyUrl is not string-mangled."""
    with_slash = FormatId(agent_url=f"{AGENT}/", id="display_300x250")
    without_slash = FormatId(agent_url=AGENT, id="display_300x250")

    assert isinstance(with_slash.agent_url, AnyUrl), "FormatId must keep agent_url typed"

    assert format_identity_or_none(with_slash) == (AGENT, "display_300x250")
    assert format_identity_or_none(with_slash) == format_identity_or_none(without_slash)


def test_product_and_package_references_compare_equal_across_url_spellings():
    """The two sides create_media_buy compares are built by different producers."""
    product_format = FormatId(agent_url=f"{AGENT}/", id="display_300x250")
    package_format = {"agent_url": AGENT, "id": "display_300x250"}  # off the wire, a dict

    assert format_identity_or_none(product_format) == format_identity_or_none(package_format)


def test_display_spells_the_identity_that_was_compared():
    """An error listing supported formats must not contradict the values compared."""
    identity = format_identity_or_none(FormatId(agent_url=f"{AGENT}/", id="display_300x250"))

    assert identity is not None
    assert format_display(identity) == f"{AGENT}/display_300x250"


def test_path_is_part_of_the_identity():
    """``/mcp`` is a different endpoint, not a spelling of the origin.

    Two normalizers used to ``removesuffix("/mcp")`` before comparing, which made
    one host's MCP endpoint and its bare origin the same agent. Nothing in the pin
    asks for that; ``canonicalize_target_uri`` preserves the path.
    """
    assert format_identity_or_none(FormatId(agent_url=f"{AGENT}/mcp", id="d")) != format_identity_or_none(
        FormatId(agent_url=AGENT, id="d")
    )


def test_case_port_and_fragment_are_canonicalized_away():
    """What a trim could never do, and what the pin's canonical form requires."""
    noisy = {"agent_url": "https://Creative.AdContextProtocol.org:443/#section", "id": "d"}

    assert format_identity_or_none(noisy) == (AGENT, "d")
