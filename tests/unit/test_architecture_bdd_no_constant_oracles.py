#!/usr/bin/env python3
"""Guard: a BDD oracle must not read a value that is really a hardcoded constant.

Two shapes, one failure mode. In both, a Then step looks like it compares the response against
something the scenario set up, but the value it compares against is baked into the step, so the
assertion holds no matter what production does.

**Rule A — a defaulted read inside an oracle (the primary rule).**
``requested.get("post_click_interval", 7)`` reads as "what the scenario asked for" and evaluates to
``7`` whenever the key is missing. The attribution-echo oracle (#1600) survived precisely because the hardcoded default
happened to equal the only scenario's request: the suite was green while asserting nothing, and
neither review nor CI could see it.

The rule deliberately ignores the CONTAINER. A guard that only watched ``ctx`` would miss
``ctx["dispatched_kwargs"].get("post_click_interval", 7)`` — 1zy8's exact shape one level down —
and would then certify as clean the very bug it exists to prevent.

**Rule B — a ctx key that no step writes.**
A read of a never-written key is dead code at best. With a default it is Rule A with extra steps;
without one it at least raises. An AST census found 18 such keys, so this accretes rather than
being a one-off.

Reads counted for Rule B include the blessed loud-read helpers ``_require(ctx, "k")``,
``_require_response(ctx)`` and ``_require_error(ctx)`` — the forms a correct fix adopts. Counting
only ``ctx["k"]`` / ``ctx.get("k")`` would flag correctly-written call sites while letting badly
written ones through: after the 1zy8 fix added a ``_require`` read, the naive census's read count
went DOWN.

Both allowlists may only SHRINK. Entries are keyed by (module, function, key) rather than by line so
that unrelated edits do not silently retire an entry, and a stale entry fails rather than lingering.

GitHub: #1600 (this guard and the oracle instances it was written from)
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.architecture

BDD_ROOT = pathlib.Path(__file__).resolve().parents[1] / "bdd"

# Functions whose body IS an oracle. A defaulted read anywhere else (a When building a request, a
# Given seeding data) is ordinary optional-argument handling, not a silent assertion.
ORACLE_PREFIXES = ("then_", "assert_", "_assert")

LOUD_READ_HELPERS = {"_require", "_require_response", "_require_error"}


# --- Rule A allowlist: defaulted reads inside oracles, keyed "module::function::key" -------------
# MAY ONLY SHRINK. Each entry is an oracle that can return a constant. Fix by deriving the expected
# value from what the scenario actually dispatched (and reading it loudly with _require), not by
# adding an entry here.
# --- Rule A allowlist: defaulted reads inside oracles, keyed "module::function::key" -------------
# MAY ONLY SHRINK. Each entry is an oracle that can return a constant. Fix by deriving the expected
# value from what the scenario actually dispatched — ctx["dispatched_kwargs"], read with _require —
# not by adding an entry here.
#
# Seeded at 79 by measurement. The empty-container defaults (`ctx.get("k", {})`) dominate that count
# and are the dangerous ones: the read looks structural, so nothing about it says "constant". A real
# instance was written WHILE fixing the guarded-assertion sweep (#1600), with this guard already green, because the
# detector did not yet treat {} as a default.
_ALLOWED_DEFAULTED_READS: frozenset[str] = frozenset(
    {
        "domain/admin_accounts.py::then_redirect_to_login::Location",
        "domain/admin_accounts.py::then_redirected_to_create::Location",
        "domain/admin_accounts.py::then_redirected_to_detail::Location",
        "domain/admin_accounts.py::then_redirected_to_list::Location",
        "domain/uc001_discover_inventory.py::then_contains_products_array::format_ids",
        "domain/uc002_create_media_buy.py::_assert_error_outcome::adcp_error",
        "domain/uc002_create_media_buy.py::then_error_references_missing_field::loc",
        "domain/uc002_create_media_buy.py::then_order_name_differs::remembered",
        "domain/uc002_create_media_buy.py::then_response_equals_remembered::remembered",
        "domain/uc002_create_media_buy.py::then_response_not_equals_remembered::remembered",
        "domain/uc002_create_paused.py::then_persisted_media_buy_is_paused::request_kwargs",
        "domain/uc002_create_paused.py::then_persisted_packages_paused::request_kwargs",
        "domain/uc002_create_paused.py::then_response_packages_report_paused::request_kwargs",
        "domain/uc002_nfr.py::then_auth_before_business_logic::request_kwargs",
        "domain/uc002_nfr.py::then_budget_validated_against_min_order::code",
        "domain/uc002_nfr.py::then_budget_validated_against_min_order::request_kwargs",
        "domain/uc002_nfr.py::then_payload_size_limits::code",
        "domain/uc002_nfr.py::then_payload_size_limits::request_kwargs",
        "domain/uc002_nfr.py::then_rate_limiting_enforced::request_kwargs",
        "domain/uc004_delivery.py::_assert_valid_content::request_params",
        "domain/uc004_delivery.py::then_attribution_echo::post_click_interval",
        "domain/uc004_delivery.py::then_attribution_echo::post_click_unit",
        "domain/uc004_delivery.py::then_attribution_echo::request_attribution",
        "domain/uc004_delivery.py::then_bearer_header::webhook_bearer_token",
        "domain/uc004_delivery.py::then_filter_result::request_params",
        "domain/uc004_delivery.py::then_first_sequence::json",
        "domain/uc004_delivery.py::then_has_deliveries_field::request_params",
        "domain/uc004_delivery.py::then_hmac_computation::X-Webhook-Signature",
        "domain/uc004_delivery.py::then_hmac_computation::X-Webhook-Timestamp",
        "domain/uc004_delivery.py::then_hmac_computation::webhook_secret",
        "domain/uc004_delivery.py::then_sequence_ascending::json",
        "domain/uc004_delivery.py::then_skip_no_webhook::json",
        "domain/uc004_delivery.py::then_webhook_payload_has_metrics::impressions",
        "domain/uc004_delivery.py::then_webhook_payload_has_metrics::spend",
        "domain/uc004_delivery.py::then_webhook_post::url",
        "domain/uc004_delivery.py::then_webhook_post::webhook_url",
        "domain/uc006_sync_creatives.py::then_asset_has_provenance_not_inherited::assets",
        "domain/uc006_sync_creatives.py::then_asset_has_provenance_not_inherited::provenance",
        "domain/uc006_sync_creatives.py::then_assignment_errors_contain_package_id::assignments",
        "domain/uc006_sync_creatives.py::then_assignment_processing_should_abort::nonexistent_package_id",
        "domain/uc006_sync_creatives.py::then_creative_a_more_delivery_than_b::assignment_weights",
        "domain/uc006_sync_creatives.py::then_existing_data_preserved::existing_generative_data",
        "domain/uc006_sync_creatives.py::then_no_field_level_merging::assets",
        "domain/uc006_sync_creatives.py::then_no_field_level_merging::provenance",
        "domain/uc006_sync_creatives.py::then_operation_fails_with_assignment_error::creative_format_id",
        "domain/uc006_sync_creatives.py::then_proceed_with_resolved_account::tenant_id",
        "domain/uc006_sync_creatives.py::then_user_assets_priority_over_generated::assets",
        "domain/uc006_sync_creatives.py::then_user_assets_priority_over_generated::user_provided_assets",
        "domain/uc008_signals.py::then_pricing_options_shape::pricing_options",
        "domain/uc009_performance.py::then_audit_log_entry::avg_performance_index",
        "domain/uc011_accounts.py::then_db_field_unchanged::original_field_values",
        "domain/uc011_accounts.py::then_error_invalid_status::loc",
        "domain/uc011_accounts.py::then_field_validation_error::loc",
        "domain/uc011_accounts.py::then_none_belong_to_agent::agent_account_ids",
        "domain/uc011_accounts.py::then_only_agent_a_deactivated::agents",
        "domain/uc019_query_media_buys.py::then_any_status_returned::seeded_media_buys",
        "domain/uc019_query_media_buys.py::then_buyer_campaign_ref_for_correlation::seeded_media_buys",
        "domain/uc019_query_media_buys.py::then_error_field_validation::field",
        "domain/uc019_query_media_buys.py::then_error_field_validation::message",
        "domain/uc019_query_media_buys.py::then_response_count_scoped::seeded_media_buys",
        "domain/uc019_query_media_buys.py::then_snapshot_field_amount::expected_snapshots",
        "domain/uc019_query_media_buys.py::then_snapshot_field_count::expected_snapshots",
        "domain/uc026_package_media_buy.py::then_package_all_fields::packages",
        "domain/uc026_package_media_buy.py::then_package_all_fields::request_kwargs",
        "generic/then_error.py::then_error_format_id_structure::loc",
        "generic/then_error.py::then_error_has_fix_suggestion::msg",
        "generic/then_media_buy.py::then_package_budget_persisted::packages",
        "generic/then_media_buy.py::then_package_budget_persisted::update_kwargs",
        "generic/then_media_buy.py::then_package_records_persisted::packages",
        "generic/then_media_buy.py::then_package_records_persisted::request_kwargs",
        "generic/then_media_buy.py::then_response_has_packages::request_kwargs",
        "generic/then_payload.py::_assert_filter_content::known_format_ids",
        "generic/then_payload.py::_assert_filter_content::known_input_format_ids",
        "generic/then_payload.py::_assert_filter_content::known_output_format_ids",
        "generic/then_payload.py::_assert_filter_content::registry_formats",
        "generic/then_payload.py::_assert_returned_formats_subset_of_registry::registry_formats",
        "generic/then_payload.py::then_all_formats::registry_formats",
        "generic/then_payload.py::then_has_referrals::creative_agent_referrals",
        "generic/then_payload.py::then_only_display::registry_formats",
    }
)


# --- Rule B allowlist: ctx keys read but never written -------------------------------------------
# MAY ONLY SHRINK. #1600 fixed the four that supplied a default (the silent-constant
# form); these are the remainder, which raise or yield None rather than silently constant-ing.
_ALLOWED_ORPHAN_KEYS: frozenset[str] = frozenset(
    {
        "bad_package_id",
        "captured_logs",
        "dispatched_pipeline",
        "e2e_config",
        "existing_product",
        "expected_existing_package_id",
        "explicit_buying_mode",
        "last_order_name",
        "media_buy_id",
        "request_attribution",  # the attribution-echo oracle's key (#1600) — still read, still never written
        "request_push_config",
        "seeded_task_count",
        "target_media_buy_id",
        "webhook_url",
    }
)


def _is_literal_default(node: ast.expr) -> bool:
    """True for a default the author wrote inline — a scalar OR an empty container.

    Empty containers matter and are easy to miss: ``ctx.get("request_params", {})`` is not an
    ``ast.Constant``, and skipping it let a real instance through — a uc004 oracle read
    ``ctx.get("request_params", {}).get("include_package_daily_breakdown")`` where nothing ever
    wrote that key, so the flag read as False for every row and the oracle asserted the opposite of
    what the scenario requested. That was written WHILE fixing the guarded-assertion sweep (#1600), with this guard
    already in place and green.
    """
    if isinstance(node, ast.Constant):
        return True
    return isinstance(node, ast.Dict | ast.List | ast.Set | ast.Tuple) and not (
        getattr(node, "elts", None) or getattr(node, "keys", None)
    )


def find_defaulted_oracle_reads(source: str, module_label: str = "<test>") -> list[tuple[str, int, str]]:
    """Return (allowlist_key, lineno, snippet) for every ``X.get("k", <literal>)`` inside an oracle."""
    hits: list[tuple[str, int, str]] = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) or not fn.name.startswith(ORACLE_PREFIXES):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and _is_literal_default(node.args[1])
            ):
                key = node.args[0].value
                hits.append((f"{module_label}::{fn.name}::{key}", node.lineno, ast.unparse(node)[:90]))
    return hits


def collect_ctx_key_usage(source: str) -> tuple[set[str], dict[str, int]]:
    """Return (keys written, {key read -> first line}) for one module."""
    written: set[str] = set()
    read: dict[str, int] = {}
    tree = ast.parse(source)

    def is_ctx(node: ast.expr) -> bool:
        return isinstance(node, ast.Name) and node.id == "ctx"

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and is_ctx(target.value)
                    and isinstance(target.slice, ast.Constant)
                ):
                    written.add(target.slice.value)
        elif (
            isinstance(node, ast.Subscript)
            and is_ctx(node.value)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.ctx, ast.Load)
        ):
            read.setdefault(node.slice.value, node.lineno)
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and is_ctx(func.value)
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                if func.attr == "setdefault":
                    written.add(node.args[0].value)
                elif func.attr == "get":
                    read.setdefault(node.args[0].value, node.lineno)
            elif (
                isinstance(func, ast.Name)
                and func.id in LOUD_READ_HELPERS
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
            ):
                read.setdefault(node.args[1].value, node.lineno)
    return written, read


def _bdd_modules() -> list[pathlib.Path]:
    return sorted(BDD_ROOT.rglob("*.py"))


class TestNoConstantOracles:
    def test_no_defaulted_reads_in_oracles(self):
        violations = []
        for path in _bdd_modules():
            label = (
                path.relative_to(BDD_ROOT / "steps").as_posix() if (BDD_ROOT / "steps") in path.parents else path.name
            )
            for key, lineno, snippet in find_defaulted_oracle_reads(path.read_text(), label):
                if key not in _ALLOWED_DEFAULTED_READS:
                    violations.append(f"{path}:{lineno}  {snippet}\n      allowlist key: {key}")

        assert not violations, (
            "Oracle reads a value that falls back to a hardcoded constant:\n  "
            + "\n  ".join(violations)
            + "\n\nWhen the key is absent the assertion compares production against the default, so "
            "it can pass with the behaviour absent. Derive the expected value from what the scenario "
            "actually dispatched and read it loudly with _require(ctx, key, hint=...)."
        )

    def test_no_orphan_ctx_keys(self):
        written: set[str] = set()
        read: dict[str, str] = {}
        for path in _bdd_modules():
            mod_written, mod_read = collect_ctx_key_usage(path.read_text())
            written |= mod_written
            for key, lineno in mod_read.items():
                read.setdefault(key, f"{path}:{lineno}")

        orphans = {key: loc for key, loc in read.items() if key not in written and key not in _ALLOWED_ORPHAN_KEYS}

        assert not orphans, (
            "ctx keys read but never written by any step:\n  "
            + "\n  ".join(f"{key}  <- {loc}" for key, loc in sorted(orphans.items()))
            + "\n\nEither the read is dead code, or it supplies a default and the oracle is a "
            "constant. Have the producing step write the key, then read it with _require()."
        )

    def test_allowlists_only_shrink(self):
        assert len(_ALLOWED_DEFAULTED_READS) <= 80, "Rule A allowlist grew — fix the oracle instead"
        assert len(_ALLOWED_ORPHAN_KEYS) <= 14, "Rule B allowlist grew — write the key instead"

    def test_no_stale_allowlist_entries(self):
        """A retired entry must be deleted, or the guard quietly covers less than it claims."""
        live_keys = set()
        live_orphan_candidates = set()
        written: set[str] = set()
        read: set[str] = set()
        for path in _bdd_modules():
            label = (
                path.relative_to(BDD_ROOT / "steps").as_posix() if (BDD_ROOT / "steps") in path.parents else path.name
            )
            live_keys |= {key for key, _, _ in find_defaulted_oracle_reads(path.read_text(), label)}
            mod_written, mod_read = collect_ctx_key_usage(path.read_text())
            written |= mod_written
            read |= set(mod_read)
        live_orphan_candidates = read - written

        stale_a = _ALLOWED_DEFAULTED_READS - live_keys
        stale_b = _ALLOWED_ORPHAN_KEYS - live_orphan_candidates
        assert not stale_a and not stale_b, (
            f"Allowlist entries no longer correspond to real violations — delete them.\n"
            f"  Rule A stale: {sorted(stale_a)}\n  Rule B stale: {sorted(stale_b)}"
        )


class TestDetectorMetaTests:
    """The detectors must catch the shapes that motivated this guard — including the subtle one."""

    def test_flags_defaulted_read_on_ctx(self):
        src = 'def then_x(ctx):\n    v = ctx.get("interval", 7)\n    assert v == 7\n'
        assert [k for k, _, _ in find_defaulted_oracle_reads(src, "m.py")] == ["m.py::then_x::interval"]

    def test_flags_defaulted_read_one_level_down(self):
        """The attribution-echo oracle's actual shape (#1600). A ctx-only guard certifies this as clean."""
        src = 'def then_x(ctx):\n    v = ctx["dispatched_kwargs"].get("post_click_interval", 7)\n    assert v == 7\n'
        assert [k for k, _, _ in find_defaulted_oracle_reads(src, "m.py")] == ["m.py::then_x::post_click_interval"]

    def test_flags_defaulted_read_on_an_arbitrary_container(self):
        src = 'def _assert_y(resp):\n    assert resp.headers.get("X-Thing", "") == "v"\n'
        assert [k for k, _, _ in find_defaulted_oracle_reads(src, "m.py")] == ["m.py::_assert_y::X-Thing"]

    def test_does_not_flag_undefaulted_get(self):
        """``.get("k")`` yields None and fails the assertion — it cannot silently constant."""
        src = 'def then_x(ctx):\n    assert ctx.get("interval") == 7\n'
        assert find_defaulted_oracle_reads(src, "m.py") == []

    def test_does_not_flag_defaulted_get_outside_an_oracle(self):
        """A When building a request may legitimately default an optional argument."""
        src = 'def when_x(ctx):\n    v = ctx.get("interval", 7)\n    return v\n'
        assert find_defaulted_oracle_reads(src, "m.py") == []

    def test_counts_require_helper_as_a_read(self):
        """Missing this would flag correctly-fixed call sites and pass badly-written ones."""
        _, read = collect_ctx_key_usage('def then_x(ctx):\n    v = _require(ctx, "dispatched_kwargs")\n')
        assert "dispatched_kwargs" in read

    def test_counts_setdefault_as_a_write(self):
        written, _ = collect_ctx_key_usage('def given_x(ctx):\n    ctx.setdefault("seeded", 1)\n')
        assert "seeded" in written

    def test_orphan_detection_pairs_reads_with_writes(self):
        written, read = collect_ctx_key_usage(
            'def given_x(ctx):\n    ctx["written_key"] = 1\n\ndef then_x(ctx):\n    assert ctx["orphan_key"]\n'
        )
        assert read.keys() - written == {"orphan_key"}
