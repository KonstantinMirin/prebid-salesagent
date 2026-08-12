"""MediaBuyCreateListEnv — composite env for the post-create get_media_buys poll.

The UC-019 storyboard scenario polls get_media_buys for a buy the SAME scenario
just created, so it needs both tools in one environment and one identity. That is
what the graded storyboard step does too: AdCP 3.1.1
``dist/compliance/3.1.1/domains/media-buy/scenarios/available_actions.yaml`` →
phase ``read_persisted_buy_actions`` → step ``get_created_buy_available_actions``
sends ``media_buy_ids: ["$context.<id captured from create_media_buy>"]`` and
validates the response against ``media-buy/get-media-buys-response.json``.

Shape mirrors ``MediaBuyDualEnv`` (create + update): extend ``MediaBuyCreateEnv``
and route by request type. The get_media_buys dispatch itself is inherited from
``MediaBuyListDispatchMixin`` rather than re-implemented, so this env and
``MediaBuyListEnv`` grade the same tool through the same code.

REST is intentionally NOT routed: UC-019 is a ``_NO_REST_UC`` (get_media_buys has
no REST route, tests/bdd/conftest.py:2885-2895), so the create and list REST
bodies never both apply in one scenario and wiring an ungraded second REST path
would be speculative. The inherited create REST dispatch is left untouched.

beads: salesagent-q9e6.1.12
"""

from __future__ import annotations

from typing import Any

from src.core.schemas._base import GetMediaBuysRequest
from tests.harness.media_buy_create import MediaBuyCreateEnv
from tests.harness.media_buy_list import MediaBuyListDispatchMixin


def _is_list_request(kwargs: dict[str, Any]) -> bool:
    return isinstance(kwargs.get("req"), GetMediaBuysRequest)


class MediaBuyCreateListEnv(MediaBuyListDispatchMixin, MediaBuyCreateEnv):
    """create_media_buy env that also dispatches get_media_buys.

    A ``req=GetMediaBuysRequest(...)`` kwarg routes to the list path; anything
    else falls through to the inherited create path. ``req=`` is a free
    discriminator because both ``_run_a2a_handler`` and ``_run_mcp_wrapper``
    already flatten a request model into the flat skill/tool parameters those
    wrappers accept.

    No extra patches: get_media_buys is a pure DB read with no external services,
    and the inherited create patches target the create module only.
    """

    def call_impl(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_impl(**kwargs)
        return super().call_impl(**kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_a2a(**kwargs)
        return super().call_a2a(**kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        if _is_list_request(kwargs):
            return self._call_list_mcp(**kwargs)
        return super().call_mcp(**kwargs)
