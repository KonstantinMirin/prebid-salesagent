"""Structural guard: no webhook-signing seam call may hardcode an unsigned secret.

Backstops salesagent-47n9.15: ``order_approval_service.py`` called
``deliver_signed_webhook(..., secret=None, ...)`` with a LITERAL ``None`` --
never deriving it from the stored ``PushNotificationConfig`` -- so a config
that asked for ``authentication_type == "HMAC-SHA256"`` signing was silently
delivered unsigned, with no error. The fix threads a config-derived ``secret``
through instead. This guard AST-scans every call to the three functions that
make up the signing seam (``deliver_signed_webhook``, ``adeliver_signed_webhook``,
``prepare_signed_request`` -- see src/core/security/webhook_egress.py) and
fails if any call site hardcodes a literal ``None`` for the secret argument,
or omits it entirely (which resolves to the same implicit-None default for
the ``deliver_signed_webhook``/``adeliver_signed_webhook`` pair). A caller
that genuinely wants an unsigned delivery must still pass ``secret=None``
explicitly as a NAME bound to an expression that says why (e.g.
``secret = None  # explicitly unauthenticated``) -- but no *call site* may
spell the literal directly, because that is exactly the shape that let this
bug hide for three independent webhook implementations before it was caught
by a disease scan, not a test failure.

The allowlist is empty and expected to stay empty: the disposition table in
salesagent-47n9.15's codebase-scan atom found exactly one instance (the bug
itself, MIGRATEd by this same PR) and zero others.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import iter_call_expressions, repo_root, src_python_files

_SIGNING_SEAM_FUNCTIONS = frozenset({"deliver_signed_webhook", "adeliver_signed_webhook", "prepare_signed_request"})

# prepare_signed_request(payload, secret, headers, *, timestamp=None) -- secret
# is positional index 1. The other two are keyword-only (secret=None).
_POSITIONAL_SECRET_INDEX = {"prepare_signed_request": 1}


def _is_none_constant(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def find_hardcoded_unsigned_secret_violations(tree: ast.Module) -> list[int]:
    """Return line numbers of signing-seam calls that hardcode an unsigned secret."""
    violations: list[int] = []
    for func_name in _SIGNING_SEAM_FUNCTIONS:
        for call in iter_call_expressions(tree, func_name):
            secret_kw = next((kw for kw in call.keywords if kw.arg == "secret"), None)
            if secret_kw is not None:
                if _is_none_constant(secret_kw.value):
                    violations.append(call.lineno)
                continue

            positional_index = _POSITIONAL_SECRET_INDEX.get(func_name)
            if positional_index is not None and len(call.args) > positional_index:
                if _is_none_constant(call.args[positional_index]):
                    violations.append(call.lineno)
                continue

            # No secret= keyword and (for the keyword-only pair) no positional
            # slot to check -- the call relies on the implicit secret=None
            # default, which is the same silent-unsigned shape as a literal.
            if positional_index is None:
                violations.append(call.lineno)

    return violations


class TestNoHardcodedUnsignedWebhookSecret:
    """(a) Real src/ has zero violations -- the fixed bug plus every sibling sender."""

    def test_no_violations_in_src(self) -> None:
        repo = repo_root()
        all_violations: dict[str, list[int]] = {}
        for path in src_python_files(repo):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            lines = find_hardcoded_unsigned_secret_violations(tree)
            if lines:
                all_violations[str(path.relative_to(repo))] = lines

        assert not all_violations, (
            "Signing-seam call(s) hardcode an unsigned secret (literal None or omitted) "
            f"-- silent-unsigned delivery, the salesagent-47n9.15 disease: {all_violations}"
        )


class TestDetectorCatchesKnownBadSnippets:
    """(b) Positive meta-tests -- every hardcoded-unsigned shape is caught."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        [
            (
                "deliver_signed_webhook-literal-none-keyword",
                "deliver_signed_webhook(url, payload, secret=None, headers=h)\n",
            ),
            (
                "deliver_signed_webhook-omitted-secret",
                "deliver_signed_webhook(url, payload, headers=h)\n",
            ),
            (
                "adeliver_signed_webhook-literal-none-keyword",
                "await adeliver_signed_webhook(url, payload, secret=None, headers=h)\n",
            ),
            (
                "adeliver_signed_webhook-omitted-secret",
                "await adeliver_signed_webhook(url, payload, headers=h)\n",
            ),
            (
                "prepare_signed_request-literal-none-positional",
                "prepare_signed_request(payload, None, headers)\n",
            ),
            (
                "prepare_signed_request-literal-none-keyword",
                "prepare_signed_request(payload, headers=headers, secret=None)\n",
            ),
        ],
    )
    def test_catches_known_bad_snippet(self, label: str, snippet: str) -> None:
        tree = ast.parse(snippet, filename=f"<known-bad:{label}>")
        assert find_hardcoded_unsigned_secret_violations(tree), f"detector missed known-bad snippet: {label}"


class TestDetectorAllowsSignedCalls:
    """(c) Negative meta-tests -- a config-derived secret is never flagged."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        [
            (
                "deliver_signed_webhook-derived-variable",
                "deliver_signed_webhook(url, payload, secret=secret, headers=h)\n",
            ),
            (
                "adeliver_signed_webhook-derived-attribute",
                "await adeliver_signed_webhook(url, payload, secret=config.webhook_secret, headers=h)\n",
            ),
            (
                "prepare_signed_request-derived-positional",
                "prepare_signed_request(payload, secret, headers)\n",
            ),
            (
                "prepare_signed_request-derived-keyword",
                "prepare_signed_request(payload, headers=headers, secret=secret)\n",
            ),
            (
                "unrelated-call-not-in-seam",
                "some_other_function(url, payload, secret=None, headers=h)\n",
            ),
        ],
    )
    def test_allows_clean_snippet(self, label: str, snippet: str) -> None:
        tree = ast.parse(snippet, filename=f"<known-good:{label}>")
        assert not find_hardcoded_unsigned_secret_violations(tree), f"detector false-flagged clean snippet: {label}"
