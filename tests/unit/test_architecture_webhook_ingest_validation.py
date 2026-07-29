"""Guard: a tool module that handles a buyer webhook URL uses the ingest helpers.

``push_notification_config.url`` and ``reporting_webhook.url`` are URLs the
protocol surface STORES now and DIALS later — by delivery time there is no
request left to refuse into, so the buyer-actionable refusal has to happen at
ingest, through ``src/core/webhook_ingest.py`` (which delegates the verdict to
the egress seam and names ``error.field``). The salesagent-w97e disease scan
found five hand-rolled copies of "pull ``url`` out of the config and store it",
none of which validated; the fix routed every protocol ingest of those fields
through the two helpers.

This guard is the class-level half of that fix: a NEW tool under
``src/core/tools/`` that accepts either field and forgets the helper fails
``make quality`` here, instead of shipping the sixth unvalidated copy. The
check is deliberately import-level — whether the module CALLS the helper on
the right value is semantic and belongs to the integration tests
(``tests/integration/test_webhook_url_ingest_refusal.py``); what is mechanical
is that a tools module which names these fields at all must at least be built
against the ingest module. The repository ``upsert`` is deliberately NOT the
enforcement point (it cannot know the request path, so ``error.field`` would
be lost — disposition row 19 of the scan).
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import parse_module, rel, repo_root

INGEST_MODULE = "src.core.webhook_ingest"
WEBHOOK_FIELD_NAMES = frozenset({"push_notification_config", "reporting_webhook"})

# Tool modules that legitimately name the fields WITHOUT importing the ingest
# helpers. Reasons in writing, like the no_call_site_backoff allowlist — these
# are correct designs, not debt, so no FIXME. The set may only shrink.
ALLOWLIST = frozenset(
    {
        # Transport wrappers: they FORWARD the raw field to _sync_creatives_impl,
        # which runs the helper. Validating in the wrapper would be the layer
        # inversion pattern #5 forbids (and a second verdict per transport).
        "src/core/tools/creatives/sync_wrappers.py",
        # Stores the config into workflow request_data AFTER _sync.py's ingest
        # verdict accepted it — a post-validation writer, same standing as the
        # delivery-time readers (scan disposition row 14).
        "src/core/tools/creatives/_workflow.py",
    }
)

FIX_HINT = (
    "This module handles push_notification_config / reporting_webhook — buyer URLs that are "
    "stored now and dialled later. Route them through validated_push_notification_config / "
    "validated_reporting_webhook (src/core/webhook_ingest.py) at ingest, so a URL the egress "
    "seam will never dial is refused with INVALID_REQUEST + error.field while the buyer's "
    "request still exists to carry the refusal."
)


def module_names_webhook_fields(tree: ast.Module) -> bool:
    """True when the module refers to either webhook field by name.

    All the shapes the field arrives in are covered: a function parameter
    (``push_notification_config=None``), an attribute read
    (``req.reporting_webhook``), a bare name, or a string key
    (``params.get("push_notification_config")``). Over-matching (a comment
    cannot match; a docstring constant can) is acceptable: the allowlist is
    the pressure valve and a false positive surfaces at the PR, not at a buyer.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg in WEBHOOK_FIELD_NAMES:
            return True
        if isinstance(node, ast.Name) and node.id in WEBHOOK_FIELD_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in WEBHOOK_FIELD_NAMES:
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in WEBHOOK_FIELD_NAMES:
            return True
    return False


def module_imports_ingest_helpers(tree: ast.Module) -> bool:
    """True when the module imports from ``src.core.webhook_ingest``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == INGEST_MODULE:
            return True
        if isinstance(node, ast.Import) and any(alias.name == INGEST_MODULE for alias in node.names):
            return True
    return False


def find_unguarded_modules() -> list[str]:
    """Tool modules naming a webhook field with no ingest-helper import."""
    tools_dir = repo_root() / "src" / "core" / "tools"
    violations: list[str] = []
    for path in sorted(tools_dir.rglob("*.py")):
        relpath = rel(path)
        if relpath in ALLOWLIST:
            continue
        tree = parse_module(path)
        if module_names_webhook_fields(tree) and not module_imports_ingest_helpers(tree):
            violations.append(relpath)
    return violations


@pytest.mark.arch_guard
def test_tool_modules_handling_webhook_urls_use_the_ingest_helpers():
    violations = find_unguarded_modules()
    assert violations == [], f"{FIX_HINT}\nUnguarded modules: {violations}"


@pytest.mark.arch_guard
def test_allowlist_only_shrinks():
    """Stale-entry check: an allowlisted module that stopped naming the fields

    (or started importing the helpers) must leave the allowlist, so the list
    can only shrink and never quietly masks a live violation.
    """
    tools_dir = repo_root() / "src" / "core" / "tools"
    for relpath in sorted(ALLOWLIST):
        path = repo_root() / relpath
        assert path.exists(), f"stale allowlist entry (file gone): {relpath}"
        tree = parse_module(path)
        assert module_names_webhook_fields(tree) and not module_imports_ingest_helpers(tree), (
            f"stale allowlist entry — {relpath} no longer needs it; remove the entry"
        )
    assert len(ALLOWLIST) <= 2, "the allowlist may only shrink — fix the new module instead of listing it"


# ── Meta-tests: the detector itself ─────────────────────────────────


@pytest.mark.arch_guard
def test_detector_flags_a_module_that_names_the_field_without_the_helper():
    """Positive: every arrival shape of the field is caught without the import."""
    shapes = [
        "def _impl(req, push_notification_config=None):\n    return push_notification_config\n",
        "def _impl(req):\n    return req.reporting_webhook\n",
        'def _impl(params):\n    return params.get("push_notification_config")\n',
    ]
    for src in shapes:
        tree = ast.parse(src)
        assert module_names_webhook_fields(tree), f"detector missed: {src!r}"
        assert not module_imports_ingest_helpers(tree)


@pytest.mark.arch_guard
def test_detector_passes_a_module_with_the_helper_or_without_the_field():
    """Negative: importing the ingest module satisfies the guard; an unrelated
    module is not in the population at all."""
    guarded = ast.parse(
        "from src.core.webhook_ingest import validated_push_notification_config\n"
        "def _impl(req, push_notification_config=None):\n"
        "    validated_push_notification_config(push_notification_config)\n"
    )
    assert module_names_webhook_fields(guarded)
    assert module_imports_ingest_helpers(guarded)

    unrelated = ast.parse("def _impl(req):\n    return req.budget\n")
    assert not module_names_webhook_fields(unrelated)
