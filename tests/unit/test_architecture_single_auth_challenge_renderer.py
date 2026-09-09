"""Guard: exactly ONE place in ``src/`` renders a 401 challenge.

Three transports each used to write their own. MCP was wrapped in
``AuthChallengeResponder``; A2A hand-rolled the identical lift inside its
integer-restoration decorator; REST set the header in its exception handler. They agreed
only by coincidence, and the coincidence broke -- an invalid credential on an auth-optional
tool was 401 AUTH_INVALID over MCP and A2A and 200 over REST, because the rule had three
homes and only two were kept in step.

The renderer is app-wide middleware now. This test fails the build if a transport starts
growing its own again, which is the failure mode a passing behavioural test cannot catch: a
fourth copy that HAPPENS to agree today is still a place someone edits tomorrow.

Scanned with AST rather than grep, so prose that merely mentions the header -- this
docstring included -- is not a violation. Only real string literals and real calls count.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit._architecture_helpers import (
    iter_call_expressions,
    repo_root,
    safe_parse,
    src_python_files,
)

REPO = repo_root()

#: The one module allowed to render a challenge.
RENDERER = REPO / "src" / "core" / "auth_middleware.py"


def _scanned() -> list[tuple[ast.Module, Path]]:
    """Every module under ``src/`` except the renderer itself."""
    out = []
    for path in sorted(src_python_files(REPO)):
        if path == RENDERER:
            continue
        tree = safe_parse(path)
        if tree is not None:
            out.append((tree, path.relative_to(REPO)))
    return out


def _docstring_constants(tree: ast.Module) -> set[int]:
    """Ids of every docstring constant, which are string literals like any other.

    A docstring EXPLAINING where the challenge is rendered is documentation, not a second
    renderer -- ``resolved_identity`` says "Rendering them as HTTP ... is the transport's
    job" and must keep saying it. Comments need no such handling: the parser drops them.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def test_only_the_renderer_writes_a_www_authenticate_header():
    """No module outside the renderer may name the header in a string literal."""
    offenders: list[str] = []
    for tree, rel in _scanned():
        docstrings = _docstring_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if "www-authenticate" in node.value.lower():
                offenders.append(f"{rel}:{node.lineno}")

    assert offenders == [], (
        "WWW-Authenticate is written outside src/core/auth_middleware.py: "
        + ", ".join(offenders)
        + ". Every transport's 401 is rendered by AuthChallengeResponder, registered as "
        "app-wide middleware in src/app.py. Adding a second writer re-creates the "
        "divergence this guard exists to prevent -- render it there or not at all."
    )


def test_only_the_renderer_decides_which_codes_get_a_challenge():
    """``challenge_for_code`` is the challenge DECISION; only the renderer may call it."""
    offenders = [
        f"{rel}:{call.lineno}" for tree, rel in _scanned() for call in iter_call_expressions(tree, "challenge_for_code")
    ]

    assert offenders == [], (
        "challenge_for_code() is called outside src/core/auth_middleware.py: "
        + ", ".join(offenders)
        + ". A caller of this is a second renderer in the making: it has asked the "
        "question whose only purpose is writing the header."
    )


def test_the_renderer_is_registered_app_wide():
    """The guard above is worthless if nothing installs the renderer.

    Pins the registration itself: ``AuthChallengeResponder`` must be added as middleware on
    the app, not wrapped around one mount. Wrapping one transport is how it covered MCP
    alone while A2A and REST wrote their own.
    """
    tree = safe_parse(REPO / "src" / "app.py")
    assert tree is not None, "src/app.py must be parseable"
    registrations = [
        call
        for call in iter_call_expressions(tree, "add_middleware")
        if any(isinstance(arg, ast.Name) and arg.id == "AuthChallengeResponder" for arg in call.args)
    ]
    assert len(registrations) == 1, (
        "src/app.py must register AuthChallengeResponder exactly once via "
        f"app.add_middleware(AuthChallengeResponder); found {len(registrations)}."
    )
