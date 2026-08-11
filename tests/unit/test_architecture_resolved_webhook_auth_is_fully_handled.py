"""Structural guard: a sender that resolves webhook auth must handle the refusal case.

The sibling guard ``test_architecture_no_inline_webhook_auth_resolution`` bans
resolving auth INLINE. It cannot see the other half of the same disease, and
salesagent-47n9.24 (GH #1893) is the proof: ``protocol_webhook_service`` called
``webhook_auth_for`` correctly, bound the result, matched ``BearerToken`` and
``SignWithSecret`` — and let ``HmacSecretMissing`` fall through to an unsigned
delivery. Every inline-resolution rule was satisfied. The buyer asked for a
signature and got none anyway.

That is the failure mode a "did you call the helper?" guard structurally cannot
catch: **calling the resolver and then dropping one of its answers on the
floor.** ``HmacSecretMissing`` exists precisely because it must NOT collapse
into ``Unauthenticated`` — one means "send it plain", the other means "the buyer
asked for a signature this sender cannot produce" — and a fall-through collapses
exactly those two.

The rule, therefore: **any module in ``src/`` that calls ``webhook_auth_for``
must also test the result against ``HmacSecretMissing``.** That is deliberately
a low bar. It cannot prove the branch REFUSES (an AST rule cannot know what
refusing means for a given sender — the three senders return ``False``, return
early, and skip a log row respectively). What it does prove is that the variant
was CONSIDERED at the site that resolved it, which is the single step all three
senders had skipped. The behavioural half — that refusing means no request
reaches a real origin — is graded at
``tests/integration/test_webhook_sender_auth_contract.py`` and
``tests/integration/test_order_approval_webhook.py``; the two are complements,
and neither alone is sufficient.

Placed in ``tests/unit/test_architecture_*.py`` with the other ~73 structural
guards, which is this repo's convention (CLAUDE.md § Structural Guards).

There is no allowlist. Every caller satisfies the rule as of salesagent-47n9.24,
and an empty rule with no escape hatch is the honest encoding of "no exceptions"
— the invariant this ticket's epic is named for. A future caller that genuinely
cannot refuse should make that argument in review, not in a set literal.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    iter_call_expressions,
    parse_module,
    rel,
    repo_root,
    src_python_files,
)

_RESOLVER_FUNCTION = "webhook_auth_for"
_REFUSAL_VARIANT = "HmacSecretMissing"

# The resolver's own module defines the variant and is not a sender.
_RESOLVER_MODULE = "src/core/security/webhook_egress.py"

_FIX_HINT = (
    f"This module calls {_RESOLVER_FUNCTION}() but never tests the result against "
    f"{_REFUSAL_VARIANT}. That variant means 'the buyer asked for a signature this sender "
    f"cannot produce' — it is NOT 'send it plain'. Letting it fall through delivers an "
    f"unsigned request to a receiver that will reject it, which is strictly worse than "
    f"delivering nothing. Add an isinstance(..., {_REFUSAL_VARIANT}) branch that refuses, "
    f"matching the three senders in src/services/."
)


def _calls_resolver(tree: ast.Module) -> bool:
    return any(True for _ in iter_call_expressions(tree, _RESOLVER_FUNCTION))


def _handles_refusal_variant(tree: ast.Module) -> bool:
    """True if the module tests something against ``HmacSecretMissing``.

    Requires the name to appear as an ARGUMENT to a call — in practice
    ``isinstance(auth, HmacSecretMissing)``. A bare mention in a docstring, a
    comment or an import does not count, which is the "would-be-missed" variant
    pinned in the meta-tests below: a substring or import-based check would call
    a module compliant for merely naming the class it ignores.
    """
    for call in iter_call_expressions(tree):
        for arg in (*call.args, *(kw.value for kw in call.keywords)):
            for node in ast.walk(arg):
                if isinstance(node, ast.Name) and node.id == _REFUSAL_VARIANT:
                    return True
                if isinstance(node, ast.Attribute) and node.attr == _REFUSAL_VARIANT:
                    return True
    return False


def find_unhandled_refusal_variant(tree: ast.Module) -> bool:
    """True if this module resolves webhook auth but ignores the refusal variant."""
    return _calls_resolver(tree) and not _handles_refusal_variant(tree)


def _violating_src_files() -> list[str]:
    repo = repo_root()
    found: list[str] = []
    for path in src_python_files(repo):
        relpath = rel(path)
        if relpath == _RESOLVER_MODULE:
            continue
        if find_unhandled_refusal_variant(parse_module(path)):
            found.append(relpath)
    return sorted(found)


class TestEveryResolverCallerHandlesTheRefusal:
    """(a) Real ``src/`` — no sender resolves auth and then ignores the refusal."""

    def test_no_src_module_ignores_the_refusal_variant(self) -> None:
        found = _violating_src_files()
        assert not found, f"{_FIX_HINT}\n\nViolating modules: {found}"

    def test_the_guard_has_subjects(self) -> None:
        """The rule must actually apply to something.

        Without this, deleting every ``webhook_auth_for`` call — or renaming the
        function — would leave the guard passing vacuously over an empty set,
        which is how a guard silently stops guarding.
        """
        repo = repo_root()
        callers = [
            rel(path)
            for path in src_python_files(repo)
            if rel(path) != _RESOLVER_MODULE and _calls_resolver(parse_module(path))
        ]
        assert len(callers) >= 3, (
            f"expected at least the three webhook senders to resolve auth through "
            f"{_RESOLVER_FUNCTION}, found {callers} — has the resolver been renamed or bypassed?"
        )


class TestDetectorCatchesKnownBadSnippets:
    """(b) Positive meta-tests — every shape of 'resolved it, then ignored it'."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        [
            (
                "matches-only-the-signable-variants",
                "auth = webhook_auth_for(c.authentication_type, c.authentication_token)\n"
                "if isinstance(auth, BearerToken):\n"
                "    headers['Authorization'] = f'Bearer {auth.token}'\n"
                "elif isinstance(auth, SignWithSecret):\n"
                "    secret = auth.secret\n",
            ),
            (
                "resolves-and-uses-nothing",
                "auth = webhook_auth_for(scheme, credentials)\n",
            ),
            (
                # The would-be-missed case: an import or a docstring naming the
                # class reads as "handled" to any substring/import-based check.
                # It is not handled — nothing branches on it.
                "names-the-variant-without-branching-on-it",
                "from src.core.security.webhook_egress import HmacSecretMissing, webhook_auth_for\n"
                "auth = webhook_auth_for(scheme, credentials)\n"
                "if isinstance(auth, SignWithSecret):\n"
                "    secret = auth.secret\n",
            ),
            (
                "keyword-resolver-call-still-counts",
                "auth = webhook_auth_for(scheme=s, credentials=c)\nif isinstance(auth, BearerToken):\n    pass\n",
            ),
        ],
    )
    def test_catches_known_bad_snippet(self, label: str, snippet: str) -> None:
        tree = ast.parse(snippet, filename=f"<known-bad:{label}>")
        assert find_unhandled_refusal_variant(tree), f"detector missed a real violation: {label}"


class TestDetectorAllowsCleanSnippets:
    """(c) Negative meta-tests — handling it, in any of its real spellings, is legal."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        [
            (
                "isinstance-guard-then-refuse",
                "auth = webhook_auth_for(scheme, credentials)\n"
                "if isinstance(auth, HmacSecretMissing):\n"
                "    logger.error('refusing to send unsigned')\n"
                "    return False\n",
            ),
            (
                "qualified-attribute-spelling",
                "auth = webhook_auth_for(scheme, credentials)\n"
                "if isinstance(auth, webhook_egress.HmacSecretMissing):\n"
                "    return False\n",
            ),
            (
                "tuple-of-variants",
                "auth = webhook_auth_for(scheme, credentials)\n"
                "if isinstance(auth, (HmacSecretMissing, Unauthenticated)):\n"
                "    return False\n",
            ),
            (
                # Modules that never resolve auth are out of scope entirely —
                # the rule is about dropping an answer you asked for.
                "module-that-never-resolves-auth",
                "headers['Authorization'] = f'Bearer {token}'\nsend(url, json=payload)\n",
            ),
        ],
    )
    def test_allows_clean_snippet(self, label: str, snippet: str) -> None:
        tree = ast.parse(snippet, filename=f"<known-good:{label}>")
        assert not find_unhandled_refusal_variant(tree), f"detector false-flagged clean snippet: {label}"
