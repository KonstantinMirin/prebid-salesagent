"""Meta-tests for creative harness environments.

Verifies that CreativeSyncEnv, CreativeListEnv, and CreativeFormatsEnv
follow the IntegrationEnv lifecycle contract: patches start/stop correctly,
mock dict populated, identity lazy, _configure_mocks called.
"""

from __future__ import annotations

import re


class TestCreativeSyncEnvContract:
    """CreativeSyncEnv must mock only external services, not DB."""

    def test_import_succeeds(self):
        """CreativeSyncEnv is importable from harness."""
        from tests.harness.creative_sync import CreativeSyncEnv

        assert CreativeSyncEnv is not None

    def test_has_correct_external_patches(self):
        """CreativeSyncEnv patches the registry instance, notifications, audit."""
        from tests.harness.creative_sync import CreativeSyncEnv

        # ai_review_executor joined the set with #1721: the ai-powered branch hands a
        # job to a real ThreadPoolExecutor that opens its OWN AdminCreativeUoW and
        # commits a review verdict, an effect that escapes the sync transaction
        # entirely. Patching it is what makes "a preview submitted no AI review" an
        # observable rather than a race.
        # slack_notifier: the Slack sender the real _send_creative_notifications reaches.
        # Patching the sender (not the function) is what lets the function's own
        # "require-human only, webhook only" guard be graded.
        #
        # "run_async" LEFT the set with salesagent-6xtxb. It patched the sync bridge
        # _sync.py calls the registry through, with ``side_effect = lambda coro: []``, so
        # the in-process catalogue was EMPTY while the e2e server fetched 71 formats from
        # the committed capture. Its only call site is the list_all_formats fetch, so
        # dropping it restored exactly that fetch and nothing else.
        expected_keys = {
            "registry",
            "send_notifications",
            "slack_notifier",
            "audit_log",
            "ai_review_executor",
        }
        assert set(CreativeSyncEnv.EXTERNAL_PATCHES.keys()) == expected_keys

    def test_is_integration_env(self):
        """CreativeSyncEnv uses real DB (use_real_db=True)."""
        from tests.harness.creative_sync import CreativeSyncEnv

        assert CreativeSyncEnv.use_real_db is True

    def test_mock_dict_populated_in_unit_mode(self):
        """Verify patches activate correctly (unit-mode smoke test without DB)."""
        from tests.harness.creative_sync import CreativeSyncEnv

        # Override use_real_db to avoid needing integration_db fixture
        class _UnitMode(CreativeSyncEnv):
            use_real_db = False

        with _UnitMode() as env:
            assert "registry" in env.mock
            assert "ai_review_executor" in env.mock
            assert "send_notifications" in env.mock
            assert "slack_notifier" in env.mock
            assert "audit_log" in env.mock
            assert len(env.mock) == 5
            # The Gemini key is a settings field, pinned on the settings object for the
            # env's lifetime rather than mocked through a config accessor.
            from src.core.config import get_settings

            assert get_settings().integrations.gemini_api_key is None

    def test_identity_defaults(self):
        """Identity has sane defaults."""
        from tests.harness.creative_sync import CreativeSyncEnv

        env = CreativeSyncEnv()
        assert env.identity.principal_id == "test_principal"
        assert env.identity.tenant_id == "test_tenant"

    def test_configure_mocks_sets_registry_defaults(self):
        """_configure_mocks installs production's testing-mode registry, not a stand-in."""
        from src.core.creative_agent_registry import ReferenceFormatsRegistry
        from tests.harness.creative_sync import CreativeSyncEnv

        class _UnitMode(CreativeSyncEnv):
            use_real_db = False

        with _UnitMode() as env:
            registry = env.mock["registry"].return_value
            assert isinstance(registry, ReferenceFormatsRegistry), (
                "the env must install production's own ReferenceFormatsRegistry: a stand-in "
                "serves a catalogue the e2e server does not have, and answers any attribute "
                "truthily (canonical_kind_for read 'spec.canonical.kind' off a MagicMock and "
                "put the repr through production code)"
            )

    def test_has_rest_endpoint(self):
        """CreativeSyncEnv defines REST_ENDPOINT for REST dispatch."""
        from tests.harness.creative_sync import CreativeSyncEnv

        assert CreativeSyncEnv.REST_ENDPOINT == "/api/v1/creatives/sync"

    def test_has_call_a2a(self):
        """CreativeSyncEnv implements call_a2a for A2A dispatch."""
        from tests.harness.creative_sync import CreativeSyncEnv

        env = CreativeSyncEnv()
        assert hasattr(env, "call_a2a")
        # Should not raise NotImplementedError (unlike base class)
        assert env.call_a2a.__func__ is not env.call_impl.__func__

    def test_has_build_rest_body(self):
        """CreativeSyncEnv implements build_rest_body for REST dispatch."""
        from tests.harness.creative_sync import CreativeSyncEnv

        env = CreativeSyncEnv()
        body = env.build_rest_body(creatives=[], dry_run=True)

        # idempotency_key AND account are present because AdCP 3.1.1 lists both in
        # sync-creatives-request /required: a REST body without them is not a valid request,
        # so the harness supplies them at every dispatch. ``account`` carries a literal id
        # here because this env has no session bound -- there is nothing to seed against
        # outside a ``with env:`` block, and this test asks for the body's SHAPE.
        # Asserted explicitly rather than loosened to a subset check -- the point of this
        # contract test is the EXACT body shape. The key's VALUE is checked by pattern
        # rather than equality: it is minted fresh per call now that sync_creatives honours
        # it, so a fixed expected value would be wrong by construction. Its shape is still
        # pinned, which is what a REST body has to get right.
        key = body.pop("idempotency_key")
        assert body == {
            "creatives": [],
            "dry_run": True,
            "account": {"account_id": "acct_unbound"},
        }
        assert re.fullmatch(r"[A-Za-z0-9_.:-]{16,255}", key), (
            f"the harness must supply a key matching the pinned pattern, got {key!r}"
        )
        assert key != env.build_rest_body(creatives=[], dry_run=True)["idempotency_key"], (
            "each dispatch must carry its OWN key -- a shared one makes two calls the same request"
        )

    def test_has_parse_rest_response(self):
        """CreativeSyncEnv implements parse_rest_response."""
        from tests.harness.creative_sync import CreativeSyncEnv

        env = CreativeSyncEnv()
        # Smoke test: should accept a dict with expected shape
        response = env.parse_rest_response({"creatives": [], "dry_run": False})
        assert response is not None

    def test_has_call_mcp(self):
        """CreativeSyncEnv implements call_mcp for MCP dispatch."""
        from tests.harness.creative_sync import CreativeSyncEnv

        env = CreativeSyncEnv()
        assert hasattr(env, "call_mcp")
        # Should be a distinct method (not inherited NotImplementedError stub)
        assert callable(env.call_mcp)


class TestCreativeListEnvContract:
    """CreativeListEnv must mock only audit logger."""

    def test_import_succeeds(self):
        """CreativeListEnv is importable from harness."""
        from tests.harness.creative_list import CreativeListEnv

        assert CreativeListEnv is not None

    def test_has_correct_external_patches(self):
        """CreativeListEnv patches audit_logger only."""
        from tests.harness.creative_list import CreativeListEnv

        expected_keys = {"audit_logger"}
        assert set(CreativeListEnv.EXTERNAL_PATCHES.keys()) == expected_keys

    def test_is_integration_env(self):
        """CreativeListEnv uses real DB."""
        from tests.harness.creative_list import CreativeListEnv

        assert CreativeListEnv.use_real_db is True

    def test_mock_dict_populated_in_unit_mode(self):
        """Verify patches activate correctly."""
        from tests.harness.creative_list import CreativeListEnv

        class _UnitMode(CreativeListEnv):
            use_real_db = False

        with _UnitMode() as env:
            assert "audit_logger" in env.mock
            assert len(env.mock) == 1


class TestCreativeFormatsEnvContract:
    """CreativeFormatsEnv must mock registry and audit logger."""

    def test_import_succeeds(self):
        """CreativeFormatsEnv is importable from harness."""
        from tests.harness.creative_formats import CreativeFormatsEnv

        assert CreativeFormatsEnv is not None

    def test_has_correct_external_patches(self):
        """CreativeFormatsEnv patches registry and audit_logger."""
        from tests.harness.creative_formats import CreativeFormatsEnv

        expected_keys = {"registry", "audit_logger"}
        assert set(CreativeFormatsEnv.EXTERNAL_PATCHES.keys()) == expected_keys

    def test_is_integration_env(self):
        """CreativeFormatsEnv uses real DB."""
        from tests.harness.creative_formats import CreativeFormatsEnv

        assert CreativeFormatsEnv.use_real_db is True

    def test_mock_dict_populated_in_unit_mode(self):
        """Verify patches activate correctly."""
        from tests.harness.creative_formats import CreativeFormatsEnv

        class _UnitMode(CreativeFormatsEnv):
            use_real_db = False

        with _UnitMode() as env:
            assert "registry" in env.mock
            assert "audit_logger" in env.mock
            assert len(env.mock) == 2


class TestInProcessCatalogueParity:
    """The in-process catalogue and the e2e server's catalogue must be the SAME SET.

    THE DIVERGENCE THIS EXISTS TO CATCH, measured and now fixed (salesagent-6xtxb):
    ``CreativeSyncEnv`` installed a ``MagicMock`` registry and blanked the sync bridge, so
    in-process transports were served an empty-or-one-format catalogue while e2e_rest was
    served the committed capture by the real server. The same BDD scenario therefore
    graded two different sellers against two different catalogues, which accounted for
    roughly 60 of 170 regressed nodeids.

    WHY THIS IS A REAL COMPARISON AND NOT A SPELLING CHECK. The e2e server's catalogue is
    not opaque: docker-compose.e2e.yml sets ``ADCP_TESTING``, so the server's
    ``get_creative_agent_registry()`` selects ``ReferenceFormatsRegistry``, whose
    ``_operator_formats_override`` reads ``tests/fixtures/creative_formats/
    reference_formats.json``; and the image is built with ``COPY . .`` (Dockerfile), so
    the file in the container is THIS tree's file, not a second copy that could drift. The
    committed fixture IS the server's catalogue. So the checkable obligation is "the
    catalogue the harness serves == the fixture", and it is graded here by running
    production's own ``list_all_formats`` on the harness registry and comparing the result
    to the fixture read independently.

    WHAT IT STILL CANNOT SEE, stated so nobody reads more into a green row than it carries:
    the SERVER is not contacted here, so this grades the harness half against the shared
    source and relies on the derivation above for the other half. A scenario-level
    comparison of ``list_creative_formats`` over e2e_rest against the same set would close
    that, and needs a running stack.

    BOTH VERDICTS ARE REACHABLE, and ``test_a_narrowed_catalogue_is_detected`` demonstrates
    it: it narrows the harness registry exactly as a scenario can and asserts the
    comparison FAILS. Without that, a parity assertion over two reads of one file could be
    green because it compares nothing.
    """

    @staticmethod
    def _capture_ids() -> set[str]:
        """The e2e server's catalogue, read from the committed fixture it serves."""
        from src.core.format_cache import load_reference_formats

        return {fmt.format_id.id for fmt in load_reference_formats()}

    @staticmethod
    def _in_process_ids(registry) -> set[str]:
        """What the harness serves, through PRODUCTION's own list_all_formats."""
        import asyncio

        formats = asyncio.run(registry.list_all_formats(tenant_id="parity_tenant"))
        return {fmt.format_id.id for fmt in formats}

    def test_harness_registry_serves_exactly_the_committed_capture(self):
        from tests.harness.creative_sync import HarnessCreativeAgentRegistry

        capture = self._capture_ids()
        assert capture, "the committed capture is empty — load_reference_formats would have raised"
        assert self._in_process_ids(HarnessCreativeAgentRegistry()) == capture

    def test_a_narrowed_catalogue_is_detected(self):
        """The red verdict, landed on purpose: the comparison can fail."""
        from src.core.format_cache import load_reference_formats
        from tests.harness.creative_sync import HarnessCreativeAgentRegistry

        registry = HarnessCreativeAgentRegistry()
        registry.serve_only(list(load_reference_formats())[:1])
        narrowed = self._in_process_ids(registry)
        assert len(narrowed) == 1
        assert narrowed != self._capture_ids(), (
            "a one-format catalogue compared EQUAL to the 71-format capture, so the parity "
            "assertion above is vacuous and would not have caught the divergence it names"
        )

    def test_the_envs_default_agent_url_is_the_captures_own(self):
        """The other half of a format reference, and the half that decides hermeticity.

        ``find_format`` matches on the PAIR ``(canonical agent_url, id)``, so a harness
        naming a different agent resolves to nothing even with a captured id — and
        ``_is_operator_agent`` is what keeps ``_validation.py``'s ``get_format`` off the
        egress seam. Measured at ADCP_TESTING=true with ``asend`` instrumented: the
        previous value ``https://creative.test.example.com`` DIALLED
        ``https://creative.test.example.com/mcp``, and the capture's own agent does not.
        """
        from src.core.format_cache import load_reference_formats
        from src.core.schemas import canonical_agent_url
        from tests.harness.creative_sync import CreativeSyncEnv

        captured_agents = {canonical_agent_url(str(fmt.format_id.agent_url)) for fmt in load_reference_formats()}
        assert canonical_agent_url(CreativeSyncEnv.DEFAULT_AGENT_URL) in captured_agents

    def test_served_format_refuses_an_id_the_capture_does_not_carry(self):
        """A harness that cannot fabricate is the mechanism, not a convention.

        ``display_300x250`` is the id the harness fabricated for years. The capture does
        not carry it (its 300x250 formats are ``_image``, ``_image_2x``, ``_image_1x_2x``,
        ``_html``, ``_generative``), production answers ``None`` for it and refuses the
        creative, and the refusal must now reach a scenario author instead of being
        papered over by an invented ``Format``.
        """
        import pytest

        from tests.harness.creative_sync import CreativeSyncEnv

        class _UnitMode(CreativeSyncEnv):
            use_real_db = False

        with _UnitMode() as env:
            with pytest.raises(KeyError, match="not in the pinned reference capture"):
                env.served_format("display_300x250")
            # ...and the capture's own id resolves, so the refusal is about the id and not
            # about the lookup being broken.
            assert env.served_format("display_300x250_image").format_id.id == "display_300x250_image"
            # A static format declared generative is refused too: the capture decides.
            with pytest.raises(KeyError, match="is static, but the scenario declared generative"):
                env.served_format("display_300x250_image", generative=True)
            assert env.served_format("display_300x250_generative", generative=True) is not None
