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

REST is routed too, and has to be: ``get_media_buys`` answers on
``POST /api/v1/media-buys/query`` and ``_NO_REST_UC_TAG_PREFIXES`` is now EMPTY
(tests/bdd/conftest.py), so every UC-019 scenario — this composite's included — is
parametrized on rest and e2e_rest. The list arm switches the endpoint, the body
builder and the response parser together, exactly as ``AccountSyncEnv`` switches
between its two verbs; the create arm is untouched.

GH #1900
"""

from __future__ import annotations

from typing import Any

from tests.harness.media_buy_create import MediaBuyCreateEnv
from tests.harness.media_buy_list import MediaBuyListDispatchMixin

# The list-vs-create discriminator is ``MediaBuyListDispatchMixin.is_list_request``,
# inherited rather than restated here: a local copy is a second definition of the
# same predicate, and the transport whose copy went stale would dispatch a different
# tool than the other three (CLAUDE.md DRY invariant).


class MediaBuyCreateListEnv(MediaBuyListDispatchMixin, MediaBuyCreateEnv):
    """create_media_buy env that also dispatches get_media_buys.

    A ``req=GetMediaBuysRequest(...)`` kwarg routes to the list path; anything
    else falls through to the inherited create path. ``req=`` is a free
    discriminator because the dispatchers this env actually uses —
    ``_run_a2a_handler`` and ``_run_mcp_client`` (MediaBuyListDispatchMixin.call_mcp
    and MediaBuyCreateEnv.call_mcp both route through the latter) — already flatten
    a request model into the flat skill/tool parameters those wrappers accept.
    Not ``_run_mcp_wrapper``: it is deprecated, no env here calls it, and unlike
    ``_run_mcp_client`` it never stashes the real MCP wire.

    No extra patches: get_media_buys is a pure DB read with no external services,
    and the inherited create patches target the create module only.
    """

    def call_impl(self, **kwargs: Any) -> Any:
        if self.is_list_request(kwargs):
            return self._call_list_impl(**kwargs)
        return super().call_impl(**kwargs)

    def call_a2a(self, **kwargs: Any) -> Any:
        if self.is_list_request(kwargs):
            return self._call_list_a2a(**kwargs)
        return super().call_a2a(**kwargs)

    def call_mcp(self, **kwargs: Any) -> Any:
        if self.is_list_request(kwargs):
            return self._call_list_mcp(**kwargs)
        return super().call_mcp(**kwargs)

    # -- REST: one env, two endpoints -----------------------------------------
    #
    # ``_active_list`` is set by BOTH writers below, unconditionally, because the two
    # REST paths read ``REST_ENDPOINT`` in OPPOSITE orders: ``RestE2EDispatcher``
    # calls ``build_rest_body`` first and then reads the attribute, while the
    # in-process ``call_rest`` reads the attribute BEFORE building the body. Setting
    # the flag in both makes either order correct, and setting it unconditionally
    # means a create request always clears the flag a preceding list request left.
    # (The ``AccountSyncEnv`` shape, for the identical two-verb reason.)
    _active_list: bool = False

    @property
    def REST_ENDPOINT(self) -> str:  # noqa: N802 — matches the inherited class-attr name
        """The list route for a get_media_buys dispatch; the inherited one otherwise.

        A @property because the verb is only known once the request is in hand, and
        the E2E dispatcher reads this attribute directly. ``super()`` and not a
        literal: ``MediaBuyCreateUpdateListEnv`` linearizes ``MediaBuyDualEnv`` behind
        this class, whose own ``REST_ENDPOINT`` property carries the per-id PUT URL an
        update needs — naming ``/api/v1/media-buys`` here would silently send every
        update in that composite to the create endpoint.
        """
        if self._active_list:
            return self.LIST_REST_ENDPOINT
        return super().REST_ENDPOINT

    @property
    def REST_METHOD(self) -> str:  # noqa: N802 — dispatcher reads getattr(env, "REST_METHOD", "post")
        """POST for the list route, whatever the primary verb uses otherwise.

        Declared for the same reason as ``REST_ENDPOINT``: under
        ``MediaBuyCreateUpdateListEnv`` the inherited property answers "put" whenever
        the update flag is set, and this class's list arm returns from
        ``build_rest_body`` before that flag is recomputed — so a list dispatch
        following an update would otherwise PUT the query route. ``getattr`` over the
        proxy because the plain create env declares no such attribute and the
        dispatcher's own default is "post".
        """
        if self._active_list:
            return "post"
        return getattr(super(), "REST_METHOD", "post")

    def _run_rest_request(self, endpoint: str, **kwargs: Any) -> Any:
        """Route the in-process REST call to the endpoint of the verb being dispatched.

        ``call_rest`` resolved ``endpoint`` from ``REST_ENDPOINT`` before the flag for
        THIS request was set, so the list arm recomputes it. The other arm forwards
        the argument UNCHANGED rather than recomputing: below this class sits
        ``MediaBuyDualEnv``, whose ``REST_ENDPOINT`` is a property over its own
        create-vs-update flag that is not set until its ``_run_rest_request`` runs —
        reading it here would resolve against the PREVIOUS request's verb.
        """
        self._active_list = self.is_list_request(kwargs)
        if self._active_list:
            endpoint = self.LIST_REST_ENDPOINT
        return super()._run_rest_request(endpoint, **kwargs)

    def build_rest_body(self, **kwargs: Any) -> dict[str, Any]:
        """Build the body of whichever verb is being dispatched.

        This used to ``pytest.fail`` on the list arm, on the ground that
        ``get_media_buys`` had no REST route. It has one —
        ``@router.post("/media-buys/query")`` — and ``_NO_REST_UC_TAG_PREFIXES`` is
        empty, so UC-019 IS parametrized on rest and e2e_rest. The refusal therefore
        stopped guarding an un-routed transport and started failing a graded one.

        Building the create body for a list request is not an option either, which is
        what the refusal was protecting against: it is create-shaped and dies inside
        ``_restore_creative_ids`` reading a ``packages`` attribute the list request
        does not have. The fix is to build the right body, not to refuse.
        """
        self._active_list = self.is_list_request(kwargs)
        if self._active_list:
            return self._build_list_rest_body(**kwargs)
        # super(), not an explicit parent call: MediaBuyCreateUpdateListEnv resolves
        # this through MediaBuyDualEnv's stateful create/update routing, which naming
        # a parent directly would bypass.
        return super().build_rest_body(**kwargs)

    def parse_rest_response(self, data: dict[str, Any]) -> Any:
        """Parse the REST body into the response model of the verb that was dispatched.

        No reset of ``_active_list`` here, unlike the ``MediaBuyDualEnv`` precedent:
        both writers above set it unconditionally at the start of every request, so a
        stale value cannot survive into the next one — and the E2E error path calls
        ``parse_rest_error_envelope`` instead of this, which would leave a
        reset-here flag stale exactly when it matters.
        """
        if self._active_list:
            return self._parse_list_rest_response(data)
        return super().parse_rest_response(data)
