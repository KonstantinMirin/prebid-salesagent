"""Contract for the ONE FormatId -> (width, height) derivation (#1600).

``parse_size_token`` and ``format_id_creative_size`` replaced three divergent local
parsers. These pin the semantics the consolidated version adopted, at the level where
they are decidable — the integration tests exercise the pricing behaviour, but a pure
parser contract belongs here, and without it a regression in the numeric check is only
observable as a downstream 500 or a silently-defaulted price.

The BOTH-SIDES-NUMERIC rule is the load-bearing one: the old dynamic-pricing parser
accepted any token containing an ``x``, so ``display_boxad`` produced the pseudo-size
``"boxad"``. Relaxing the check does not merely widen what is accepted, it makes
``int()`` raise on the non-numeric half — a 500 on buyer-supplied input at the GAM
suggest route.
"""

from __future__ import annotations

import pytest

from src.core.helpers.creative_helpers import format_id_creative_size, parse_size_token
from src.core.schemas import FormatId

AGENT = "https://creative.adcontextprotocol.org"


class TestParseSizeToken:
    @pytest.mark.parametrize(
        "token,expected",
        [
            ("300x250", (300, 250)),
            ("728x90", (728, 90)),
            # Case tolerance came from the dynamic-pricing variant: publishers write both.
            ("300X250", (300, 250)),
            ("1x1", (1, 1)),
        ],
        ids=["lower", "wide", "upper", "unit"],
    )
    def test_parses_a_wh_token(self, token: str, expected: tuple[int, int]) -> None:
        assert parse_size_token(token) == expected

    @pytest.mark.parametrize(
        "token",
        [
            "boxad",  # the pseudo-size the old parser produced
            "300xfoo",  # buyer-supplied at the GAM suggest route
            "foox250",
            "display",  # no 'x' at all
            "x",
            "300x",
            "x250",
            "",
            "300x250x100",  # partition keeps the tail: "250x100" is not a number
        ],
    )
    def test_rejects_anything_that_is_not_two_numbers(self, token: str) -> None:
        """Both sides must be numeric, and rejection must be a None — never an exception.

        The GAM suggest route feeds this raw query-string values, so raising here is a
        500 on buyer input.
        """
        assert parse_size_token(token) is None


class TestFormatIdCreativeSize:
    def test_typed_dimensions_win_over_the_id(self) -> None:
        """A parameterized FormatId carries the truth; the id token is only a fallback.

        dynamic_pricing_service consulted ONLY the id, so this case returned nothing
        while gam_inventory_service saw a size — the same FormatId, two answers.
        """
        fmt = FormatId(agent_url=AGENT, id="display_image", width=300, height=250)
        assert format_id_creative_size(fmt) == (300, 250)

    def test_typed_dimensions_beat_a_conflicting_id_token(self) -> None:
        fmt = FormatId(agent_url=AGENT, id="display_728x90_image", width=300, height=250)
        assert format_id_creative_size(fmt) == (300, 250)

    def test_falls_back_to_an_id_encoded_token(self) -> None:
        fmt = FormatId(agent_url=AGENT, id="display_300x250_image")
        assert format_id_creative_size(fmt) == (300, 250)

    def test_no_size_anywhere_is_none(self) -> None:
        """No 'display' gate: the fallback scans every token of any id (#1600)."""
        assert format_id_creative_size(FormatId(agent_url=AGENT, id="video_preroll")) is None

    def test_non_numeric_token_is_not_a_size(self) -> None:
        assert format_id_creative_size(FormatId(agent_url=AGENT, id="display_boxad")) is None
