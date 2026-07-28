"""Guard: sync_accounts builds an Account row in exactly ONE place.

Disease (#1721): the dry_run preview and the live create each described the row
they were about to write with their own field list. Nothing forced them to agree,
and they did not — the preview arm returned before any write, so a payload
carrying one natural key TWICE previewed "created" twice under two account_ids,
an outcome no real run can produce (BR-RULE-062). The buyer would use a preview
to rule out exactly that.

The fix routes both arms through ``_new_account_row``. This guard keeps them
there: inside ``src/core/tools/accounts.py`` an ``Account`` row may be
constructed only by that builder. A second construction site is how the two arms
drift apart again, and the drift is invisible until someone diffs a preview
against a real run.

Scope is this one module deliberately. Other modules legitimately build Account
rows for their own purposes (the admin create form, test factories); what cannot
be allowed is TWO builders inside the one function that must preview itself
faithfully.

Note what this guard does NOT do: it pins the mechanism, not the behaviour. The
behavioural protection is the set of dry_run tests that run the SAME payload
through preview and through a live sync and compare — the live run is the oracle,
so those tests cannot drift from the behaviour they mirror either.
"""

import ast

from tests.unit._architecture_helpers import REPO_ROOT, parse_module

MODULE = "src/core/tools/accounts.py"
BUILDER = "_new_account_row"
ORM_MODULE = "src.core.database.models"
ORM_CLASS = "Account"


def orm_row_names(tree: ast.Module) -> set[str]:
    """The local name(s) this module binds to the ORM ``Account`` model.

    Resolved from the module's own imports rather than hardcoded, because the
    Pydantic SCHEMA is also called ``Account`` here and constructing it is not a
    row construction at all. accounts.py imports the ORM model as ``DBAccount``
    precisely to keep the two apart; reading the alias means the guard follows a
    rename instead of silently going blind or crying wolf.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == ORM_MODULE:
            names.update(alias.asname or alias.name for alias in node.names if alias.name == ORM_CLASS)
    return names


def find_row_constructions_outside_builder(tree: ast.Module, row_names: set[str] | None = None) -> list[int]:
    """Line numbers where an ORM Account row is constructed outside the shared builder."""
    names = orm_row_names(tree) if row_names is None else row_names
    if not names:
        return []

    def is_row_construction(call: ast.Call) -> bool:
        return (getattr(call.func, "id", None) or getattr(call.func, "attr", None)) in names

    inside_builder: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == BUILDER:
            inside_builder.update(
                sub.lineno for sub in ast.walk(node) if isinstance(sub, ast.Call) and is_row_construction(sub)
            )

    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and is_row_construction(node) and node.lineno not in inside_builder
    )


def test_the_orm_row_alias_is_still_resolvable():
    """The guard is only as good as the alias it resolves — pin that it found one.

    If accounts.py stopped importing the ORM model under a name this can see, the
    scan above would return an empty list and pass while checking nothing.
    """
    names = orm_row_names(parse_module(REPO_ROOT / MODULE))
    assert names, f"{MODULE} no longer imports {ORM_CLASS} from {ORM_MODULE} — the guard would be inert"


def test_sync_accounts_builds_its_row_in_one_place():
    path = REPO_ROOT / MODULE
    violations = find_row_constructions_outside_builder(parse_module(path))
    assert not violations, (
        f"{MODULE} constructs an Account row outside {BUILDER}() at line(s) "
        f"{violations}. The dry_run preview and the live create must describe the SAME row — "
        "two field lists is how the preview came to claim an outcome a real run cannot "
        "produce (#1721). Route it through the shared builder."
    )


def test_guard_catches_a_second_construction_site():
    """Positive meta-test: a second builder anywhere in the module is a violation."""
    drifted = (
        "def _new_account_row(**kw):\n"
        "    return DBAccount(**kw)\n"
        "\n"
        "def _preview(entry):\n"
        "    return DBAccount(tenant_id=entry.tenant_id, name=entry.name)\n"
    )
    assert find_row_constructions_outside_builder(ast.parse(drifted), {"DBAccount"}), (
        "a construction site outside the builder must be flagged"
    )

    # The aliased form is the same defect wearing a different name.
    aliased = (
        "def _new_account_row(**kw):\n"
        "    return Account(**kw)\n"
        "\n"
        "def _preview(entry):\n"
        "    return models.Account(tenant_id=entry.tenant_id)\n"
    )
    assert find_row_constructions_outside_builder(ast.parse(aliased), {"Account"})


def test_guard_ignores_the_builder_itself_and_unrelated_calls():
    """Negative meta-test: the builder is the point, and other calls are not rows."""
    single_site = (
        "def _new_account_row(**kw):\n"
        "    return DBAccount(tenant_id=kw['t'], account_id=kw['a'])\n"
        "\n"
        "def _preview(entry):\n"
        "    return _new_account_row(t=entry.t, a=entry.a)\n"
        "\n"
        "def _other(entry):\n"
        "    return AccountRepository(session, tenant_id='t')\n"
    )
    assert find_row_constructions_outside_builder(ast.parse(single_site), {"DBAccount"}) == []
