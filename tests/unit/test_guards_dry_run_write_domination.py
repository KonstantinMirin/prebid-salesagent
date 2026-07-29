"""Guard: sync_accounts write helpers must RECEIVE dry_run.

The settings-update arm persisted under dry_run=true because its processor
never received the flag — the dispatch routed to it before any dry_run branch,
and a scan for ``if .*dry_run`` is structurally blind to an arm the flag never
reaches. This guard makes that shape un-reintroducible in accounts.py:

1. every call to ``_process_settings_update_entry`` forwards ``dry_run=``;
2. every function whose body performs a repository write (``update_fields`` /
   ``create``) has the flag in scope — a ``dry_run`` parameter or a local
   ``dry_run = ...`` binding (the impl derives it from the request) — or is an
   allowlisted live-arm-only helper.

The allowlist may only shrink. ``_apply_to_existing_account`` is live-arm-only
by construction: its single call site sits lexically after the provisioning
arm's ``if dry_run: ... continue`` block, which rule 2 cannot see — rule 1's
companion scenario coverage (BR-UC-011 dry-run partition) grades that arm
behaviorally.
"""

import ast

from tests.unit._architecture_helpers import REPO_ROOT

_ACCOUNTS_FILE = REPO_ROOT / "src" / "core" / "tools" / "accounts.py"

_WRITE_METHODS = {"update_fields", "create"}

#: Live-arm-only helpers, exempt from rule 2. May only shrink.
_LIVE_ARM_ONLY = {"_apply_to_existing_account"}

_DISPATCH_HELPER = "_process_settings_update_entry"


def _function_write_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Names of repository-write methods called anywhere in fn's body."""
    calls = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _WRITE_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"repo", "uow"}
        ):
            calls.append(node.func.attr)
    return calls


def _check_source(source: str, filename: str) -> list[str]:
    """Apply both rules to a module source; return offender descriptions."""
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            writes = _function_write_calls(node)
            if not writes:
                continue
            arg_names = {a.arg for a in [*node.args.args, *node.args.kwonlyargs]}
            binds_dry_run = any(
                isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "dry_run" for t in n.targets)
                for n in ast.walk(node)
            )
            if "dry_run" not in arg_names and not binds_dry_run and node.name not in _LIVE_ARM_ONLY:
                offenders.append(
                    f"{filename}:{node.lineno}: {node.name}() performs a repository write "
                    f"({', '.join(sorted(set(writes)))}) but takes no dry_run parameter"
                )
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            if name == _DISPATCH_HELPER:
                kwargs = {kw.arg for kw in node.keywords}
                if "dry_run" not in kwargs:
                    offenders.append(f"{filename}:{node.lineno}: call to {_DISPATCH_HELPER} does not forward dry_run=")
    return offenders


def test_sync_accounts_write_helpers_receive_dry_run():
    offenders = _check_source(_ACCOUNTS_FILE.read_text(encoding="utf-8"), str(_ACCOUNTS_FILE.relative_to(REPO_ROOT)))
    assert not offenders, (
        "A sync_accounts write path cannot receive the dry_run flag — the exact shape "
        "that let a preview persist a settings-update. Thread dry_run through (or, for a "
        "provably live-arm-only helper, extend the shrinking allowlist with rationale):\n" + "\n".join(offenders)
    )


class TestGuardMetaCases:
    """The guard's own detection contract (positive / negative)."""

    def test_flags_write_helper_without_dry_run(self):
        src = "def helper(entry, repo):\n    repo.update_fields(1, a=2)\n"
        assert _check_source(src, "m.py") != []

    def test_accepts_write_helper_with_dry_run_keyword_only(self):
        src = "def helper(entry, repo, *, dry_run=False):\n    repo.update_fields(1, a=2)\n"
        assert _check_source(src, "m.py") == []

    def test_flags_dispatch_call_without_dry_run(self):
        src = "def impl(repo):\n    _process_settings_update_entry(1, repo, None, 0)\n"
        assert _check_source(src, "m.py") != []

    def test_accepts_dispatch_call_forwarding_dry_run(self):
        src = "def impl(repo):\n    _process_settings_update_entry(1, repo, None, 0, dry_run=True)\n"
        assert _check_source(src, "m.py") == []

    def test_ignores_reads_and_non_repo_calls(self):
        src = "def helper(repo, x):\n    row = repo.get_by_id(x)\n    x.create()\n    return row\n"
        assert _check_source(src, "m.py") == []

    def test_allowlisted_live_arm_helper_is_exempt(self):
        src = "def _apply_to_existing_account(entry, existing, repo, operator):\n    repo.update_fields(1, a=2)\n"
        assert _check_source(src, "m.py") == []
