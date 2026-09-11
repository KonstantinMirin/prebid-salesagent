"""Integration tests for sync_creatives that grade something the wire cannot yet.

This file used to hold 82 tests, 75 of which asserted on ``_impl``'s returned DTO, on a
``pytest.raises`` class, or on a DB read-back -- none of which can see a wrong wire
code, because the exception class IS the authority on the code and the DTO is what the
transports serialize, not what the buyer received. Each of those rules is now graded by
a BDD scenario on every transport (BR-UC-006-sync-creatives.feature and the local
uc006 features), and the integration test that duplicated it is gone.

What remains is one of three things, and each test says which:

* its BDD owner exists but is PARKED -- a documented spec-production gap or an unwired
  step keeps the scenario xfailed, so deleting the test would lose the only grading it
  has today. The test leaves when the scenario graduates
  (.claude/rules/workflows/xpass-graduation.md);
* it grades the REQUEST MODEL, not a dispatch -- a construction-time refusal the
  boundary derives its field pointer from;
* the rule has no wire in the sync response at all (an audit-log side effect; a
  persistence claim whose wire is UC-018 list_creatives, unreachable from
  CreativeSyncEnv).
"""

from __future__ import annotations

import pytest
from adcp.types import FormatId as AdcpFormatId
from pydantic import ValidationError

from src.core.exceptions import AdCPAuthenticationError, first_validation_error_field
from tests.factories import MediaBuyFactory, MediaPackageFactory, PrincipalFactory, ProductFactory, TenantFactory
from tests.factories.creative_asset import build_assets, image_spec, make_test_banner_creative
from tests.harness import CreativeSyncEnv, make_identity
from tests.harness.transport import Transport

DEFAULT_AGENT_URL = "https://creative.adcontextprotocol.org"

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _error_codes(errors: list | None) -> list[str]:
    """Extract the machine CODE from each per-creative error entry.

    Production emits these entries TYPED (_processing.py builds each with
    build_error_object), so the code is present. The message is not read: it is a function
    of the code through CODE_TABLE, so asserting both would check the table against itself.
    """
    if not errors:
        return []
    return [str(getattr(e, "code", None) or getattr(e, "error_code", "")) for e in errors]


_make_creative_asset = make_test_banner_creative  # Canonical version from tests.factories.creative_asset
_make_identity = make_identity  # Canonical version from tests.harness


class TestSyncAuthRequired:
    """Auth errors are operation-level — raised before any creative processing.

    The missing- and empty-principal cases are graded on the wire by the
    authentication partition and boundary outlines in BR-UC-006 (AUTH_MISSING on every
    transport), so their tests are gone.
    """

    def test_identity_without_tenant_raises(self, integration_db):
        """Covers: UC-006-EXT-B-01 — tenant=None → AdCPAuthenticationError.

        KEPT: the BDD owner, @T-UC-006-ext-b (tenant not found), is parked in the UC-006
        route ledger. Until it graduates this is the only test of the no-tenant refusal.
        """
        identity = _make_identity(principal_id="p1", tenant=None)
        with CreativeSyncEnv() as env:
            with pytest.raises(AdCPAuthenticationError):
                env.call_impl(creatives=[_make_creative_asset()], identity=identity)


class TestCreativeValidation:
    """Per-creative validation outcomes whose BDD owners are parked."""

    def test_empty_name_rejected(self, integration_db):
        """Covers: UC-006-EXT-D-01 — empty creative name → failed result.

        KEPT: the BDD owner, @T-UC-006-ext-d, is parked with a ledger reason about
        plain-string errors[]; the per-item path it grades is live on the wire now (the
        BR-RULE-033 INV-1 pair and the failed-creative-assignment scenario both provoke
        this failure), so graduating ext-d is what retires this test.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            response = env.call_impl(creatives=[_make_creative_asset(name="")])
            assert len(response.creatives) == 1
            result = response.creatives[0]
            assert result.action == "failed" or (result.errors and len(result.errors) > 0)

    def test_whitespace_only_name_rejected(self, integration_db):
        """Covers: UC-006-EXT-D-01 — whitespace-only name → failed result.

        KEPT: same owner situation as the empty-name case (@T-UC-006-ext-d-whitespace).
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            response = env.call_impl(creatives=[_make_creative_asset(name="   ")])
            assert len(response.creatives) == 1
            result = response.creatives[0]
            assert result.action == "failed" or (result.errors and len(result.errors) > 0)

    def test_adapter_format_skips_registry_validation(self, integration_db):
        """Covers: UC-006-CREATIVE-FORMAT-VALIDATION-02 — adapter:// agent_url skips external format lookup.

        KEPT: the BDD owner, @T-UC-006-rule-035-inv2 (adapter format skips external
        validation), is parked in the UC-006 route ledger.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            response = env.call_impl(
                creatives=[
                    _make_creative_asset(
                        creative_id="c_adapter",
                        format_id=AdcpFormatId(agent_url="broadstreet://default", id="broadstreet_billboard"),
                    )
                ]
            )
            assert len(response.creatives) == 1
            # Should succeed without registry lookup (non-HTTP agent_url)
            assert response.creatives[0].action != "failed"


class TestValidationModeSemantics:
    """Strict vs lenient validation mode behavior with real DB savepoints.

    The response-side claims (a failed creative does not abort its siblings; strict and
    lenient assignment outcomes; CREATIVE_NOT_FOUND and PACKAGE_NOT_FOUND on the
    synthesized entries) are graded on the wire by BR-RULE-033 INV-1..INV-5, the
    validation-mode outlines and the assignment-reference scenarios in BR-UC-006.
    """

    def test_lenient_savepoint_isolation_with_real_db(self, integration_db):
        """Covers: UC-006-MAIN-MCP-05 — lenient: DB savepoints isolate per-creative failures.

        KEPT: the claim is about PERSISTENCE -- the failed creative is not in the library,
        its siblings are. Its wire is list_creatives (UC-018), which CreativeSyncEnv does
        not dispatch, so a UC-006 scenario cannot express it and the DB read-back stays.
        """
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import Creative as DBCreative

        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            env.call_impl(
                creatives=[
                    _make_creative_asset(creative_id="c_survives", name="Survivor"),
                    _make_creative_asset(creative_id="c_fails", name=""),
                    _make_creative_asset(creative_id="c_also_survives", name="Also Survivor"),
                ],
                validation_mode="lenient",
            )

        # Verify in DB: good creatives persisted despite bad creative in the batch
        with get_db_session() as session:
            survivors = session.scalars(
                select(DBCreative).filter_by(tenant_id="test_tenant", principal_id="test_principal")
            ).all()
            survivor_ids = {c.creative_id for c in survivors}
            assert "c_survives" in survivor_ids, "Good creative should be persisted"
            assert "c_also_survives" in survivor_ids, "Second good creative should be persisted"
            assert "c_fails" not in survivor_ids, "Bad creative should not be persisted"


class TestDeleteMissing:
    """delete_missing flag behavior with real DB.

    KEPT (both): the BDD owner, @T-UC-006-boundary-delete-missing, is parked because one
    of its steps has no definition, so none of its fifteen rows execute. Wiring that
    outline is what retires these two.
    """

    def test_delete_missing_archives_unlisted_creatives(self, integration_db):
        """Covers: UC-006-DELETE-MISSING-01 — unlisted creatives soft-deleted."""
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import Creative as DBCreative

        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            # Create two creatives
            env.call_impl(
                creatives=[
                    _make_creative_asset(creative_id="c_keep", name="Keep"),
                    _make_creative_asset(creative_id="c_orphan", name="Orphan"),
                ]
            )
            # Re-sync with only one — orphan should be archived
            response = env.call_impl(
                creatives=[_make_creative_asset(creative_id="c_keep", name="Keep")],
                delete_missing=True,
            )

        # Check response includes a deleted action for orphan
        actions = {r.creative_id: r.action for r in response.creatives}
        assert "deleted" in actions.values()

        with get_db_session() as session:
            orphan = session.scalars(
                select(DBCreative).filter_by(creative_id="c_orphan", tenant_id="test_tenant")
            ).first()
            assert orphan is not None
            assert orphan.status == "archived"

    def test_delete_missing_false_preserves_unlisted(self, integration_db):
        """Covers: UC-006-DELETE-MISSING-02 — default: unlisted creatives unchanged."""
        from sqlalchemy import select

        from src.core.database.database_session import get_db_session
        from src.core.database.models import Creative as DBCreative

        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            # Create initial creative
            env.call_impl(creatives=[_make_creative_asset(creative_id="c_existing", name="Existing")])
            # Sync a different creative without delete_missing
            response = env.call_impl(
                creatives=[_make_creative_asset(creative_id="c_new_one", name="New")],
                delete_missing=False,
            )

        # Only the synced creative in results
        assert len(response.creatives) == 1
        assert response.creatives[0].creative_id == "c_new_one"

        with get_db_session() as session:
            existing = session.scalars(
                select(DBCreative).filter_by(creative_id="c_existing", tenant_id="test_tenant")
            ).first()
            assert existing is not None
            assert existing.status != "archived", "Existing creative should not be archived"


class TestCreativeIdsFilter:
    """creative_ids parameter scoping."""

    def test_creative_ids_filter_narrows_processing(self, integration_db):
        """Covers: UC-006-CREATIVE-IDS-SCOPE-01 — only matching IDs processed.

        KEPT: the creative_ids rows live in @T-UC-006-boundary-delete-missing, which is
        parked on a missing step definition (see TestDeleteMissing).
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            response = env.call_impl(
                creatives=[
                    _make_creative_asset(creative_id="c1", name="One"),
                    _make_creative_asset(creative_id="c2", name="Two"),
                    _make_creative_asset(creative_id="c3", name="Three"),
                ],
                creative_ids=["c1", "c3"],
            )

        # Only c1 and c3 should be in results
        result_ids = {r.creative_id for r in response.creatives}
        assert result_ids == {"c1", "c3"}
        assert "c2" not in result_ids

    def test_empty_creative_ids_is_refused_by_the_request(self, integration_db):
        """Behavior: UC-006-CREATIVE-IDS-SCOPE-02 — an EMPTY creative_ids array is refused.

        KEPT: this grades the REQUEST MODEL, not a dispatch. creative/
        sync-creatives-request.json @ AdCP 3.1.1 gives creative_ids ``minItems: 1``, so
        an empty array is refused at construction on every transport, and the field
        pointer production derives from that refusal is what this pins.
        """
        from tests.helpers.creative_test_helpers import sync_creatives_request

        with pytest.raises(ValidationError) as exc_info:
            sync_creatives_request(
                creatives=[_make_creative_asset(creative_id="c1", name="One")],
                creative_ids=[],
            )

        assert first_validation_error_field(exc_info.value) == "creative_ids"


class TestSyncExtensions:
    """Extension scenarios whose BDD owners are parked, plus one request-model refusal."""

    def test_missing_name_field_is_refused_by_the_request(self, integration_db):
        """Covers: UC-006-EXT-D-02 — a creative without ``name`` is refused BY THE REQUEST.

        KEPT: grades the REQUEST MODEL. ``name`` is required by core/creative-asset.json
        @ AdCP 3.1.1, so the omission is refused at construction on every transport; the
        pointer must locate WHICH creative in a batch was wrong (RFC 6901, core/error.json).
        """
        from tests.helpers.creative_test_helpers import sync_creatives_request

        with pytest.raises(ValidationError) as exc_info:
            sync_creatives_request(
                creatives=[
                    {
                        "creative_id": "c_no_name",
                        "format_id": {"agent_url": DEFAULT_AGENT_URL, "id": "display_300x250"},
                        "assets": build_assets(image_spec("banner")),
                    }
                ],
            )

        assert first_validation_error_field(exc_info.value) == "creatives[0].name"

    def test_unknown_format_fails_with_hint(self, integration_db):
        """Covers: UC-006-EXT-F-01 — format not in registry → failed with hint.

        KEPT: the BDD owner, @T-UC-006-ext-f, is parked; its ledger reason names a code
        (CREATIVE_FORMAT_UNKNOWN) that the pinned enum does not define, so graduating it
        starts with correcting the scenario, not production.
        """
        from unittest.mock import AsyncMock

        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            # Override: registry.get_format returns None (format not found)
            registry_mock = env.mock["registry"].return_value
            registry_mock.get_format = AsyncMock(return_value=None)

            response = env.call_impl(
                creatives=[_make_creative_asset(creative_id="c_unknown_fmt")],
            )

        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action == "failed"
        assert "VALIDATION_ERROR" in _error_codes(result.errors)

    def test_unreachable_agent_fails_with_retry(self, integration_db):
        """Covers: UC-006-EXT-G-01 — agent unreachable → buyer told to retry.

        KEPT: the BDD owner, @T-UC-006-ext-g, is parked on a ledger reason naming a code
        (CREATIVE_AGENT_UNREACHABLE) the pinned enum does not define. This test already
        grades the wire: the registry TYPES all network failures
        (creative_agent_registry.py — connect/timeout -> AdCPServiceUnavailableError), so
        "unreachable" reaches the buyer as a transient SERVICE_UNAVAILABLE envelope.
        """
        from src.core.exceptions import AdCPServiceUnavailableError

        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")
            env.mock["registry"].return_value.get_format.side_effect = AdCPServiceUnavailableError()

            result = env.call_via(
                Transport.REST,
                creatives=[_make_creative_asset(creative_id="c_unreachable")],
            )

            assert result.is_error, f"Unreachable agent must fail the request transiently: {result.payload!r}"
            result.assert_wire_error(
                "SERVICE_UNAVAILABLE",
                recovery="transient",
            )

    def test_format_mismatch_lenient_logs_error(self, integration_db):
        """Covers: UC-006-EXT-K-02 — lenient: format mismatch → assignment_errors.

        KEPT: the BDD owner, @T-UC-006-rule-039-inv5-lenient, is parked because one of
        its steps has no definition.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            principal = PrincipalFactory(tenant=tenant, principal_id="test_principal")

            product = ProductFactory(
                tenant=tenant,
                format_ids=[{"agent_url": DEFAULT_AGENT_URL, "id": "display_300x250"}],
            )
            media_buy = MediaBuyFactory(tenant=tenant, principal=principal)
            pkg = MediaPackageFactory(
                media_buy=media_buy,
                package_config={"product_id": product.product_id, "package_id": "pkg_fmt"},
            )
            pkg_id = pkg.package_id

            response = env.call_impl(
                creatives=[
                    _make_creative_asset(
                        creative_id="c_vid",
                        name="Video",
                        format_id=AdcpFormatId(agent_url=DEFAULT_AGENT_URL, id="video_30s"),
                    )
                ],
                assignments=[{"creative_id": "c_vid", "package_id": pkg_id}],
                validation_mode="lenient",
            )

        result = response.creatives[0]
        assert result.assignment_errors is not None
        assert pkg_id in result.assignment_errors


class TestProvenanceEnforcement:
    """Provenance metadata enforcement end-to-end through sync flow.

    The absent-when-required warning, the no-policy and null-policy and
    explicitly-false cases are graded on the wire by BR-RULE-094 INV-1/INV-3/INV-4 and
    the provenance partition rows in BR-UC-006.
    """

    def test_provenance_present_no_warning(self, integration_db):
        """Covers: UC-006-PROV-02 — provenance present → no warning.

        KEPT: the BDD owner, @T-UC-006-rule-094-inv2, is parked because the payload its
        Given builds is refused by the harness's malformation gate before dispatch.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")
            ProductFactory(
                tenant=tenant,
                creative_policy={"provenance_required": True, "co_branding": "optional"},
            )

            response = env.call_impl(
                creatives=[
                    _make_creative_asset(
                        creative_id="c_with_prov",
                        name="With Provenance",
                        provenance={"digital_source_type": "digital_creation", "ai_tool": {"name": "DALL-E"}},
                    )
                ],
            )

        assert len(response.creatives) == 1
        result = response.creatives[0]
        assert result.action != "failed"
        provenance_warnings = [w for w in (result.warnings or []) if "provenance" in w.lower()]
        assert len(provenance_warnings) == 0


class TestFormatCompatibilityExtended:
    """Format compatibility in _process_assignments.

    URL canonicalization, empty product format_ids and a package without a product are
    graded on the wire by BR-RULE-039 INV-1/INV-3/INV-6.
    """

    def test_format_id_dual_key_support(self, integration_db):
        """Covers: UC-006-ASSIGNMENT-FORMAT-COMPATIBILITY-05 — 'format_id' key accepted alongside 'id'.

        KEPT: the BDD owner, @T-UC-006-rule-039-inv4, is parked in the UC-006 route ledger.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            principal = PrincipalFactory(tenant=tenant, principal_id="test_principal")
            # Product uses 'format_id' key instead of 'id'
            product = ProductFactory(
                tenant=tenant,
                format_ids=[
                    {"agent_url": DEFAULT_AGENT_URL, "format_id": "display_300x250"},
                ],
            )
            media_buy = MediaBuyFactory(tenant=tenant, principal=principal)
            pkg = MediaPackageFactory(
                media_buy=media_buy,
                package_config={"product_id": product.product_id, "package_id": "pkg_dual"},
            )

            response = env.call_impl(
                creatives=[
                    _make_creative_asset(
                        creative_id="c_dual",
                        name="Dual Key",
                        format_id=AdcpFormatId(agent_url=DEFAULT_AGENT_URL, id="display_300x250"),
                    )
                ],
                assignments=[{"creative_id": "c_dual", "package_id": pkg.package_id}],
                validation_mode="strict",
            )

        result = response.creatives[0]
        assert result.action != "failed", f"Expected success but got: {result.errors}"


class TestSyncFlowVerification:
    """Side effects with no wire in the sync response.

    The Slack-notification cases are graded on the wire-adjacent seams by BR-RULE-037
    INV-2/INV-3 (the harness's send_notifications mock is the same seam), so their
    tests are gone.
    """

    def test_sync_calls_audit_log(self, integration_db):
        """Covers: UC-006-MAIN-MCP-10 — sync operation triggers audit logging.

        KEPT: an audit-log write has no representation in the sync response, so there is
        no wire to grade it on; the mock seam is the only observation point.
        """
        with CreativeSyncEnv() as env:
            tenant = TenantFactory(tenant_id="test_tenant")
            PrincipalFactory(tenant=tenant, principal_id="test_principal")

            env.call_impl(
                creatives=[_make_creative_asset(creative_id="c_audit", name="Audit Test")],
            )

            assert env.mock["audit_log"].called, "Audit log should be called after sync"
