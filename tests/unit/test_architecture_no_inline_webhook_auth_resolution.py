"""Structural guard: no module resolves webhook auth inline, outside the resolver.

The disease, stated once: *a webhook sender resolves push-notification auth
inline from the config — picking its own FIELD and its own VALUE spelling —
instead of calling one shared resolver.* A codebase-wide enumeration
(salesagent-47n9.20) found three independent senders doing it three different
ways:

* ``order_approval_service`` compares lowercase ``"bearer"`` / ``"basic"``, and
  takes its HMAC secret from ``webhook_secret`` — a column with ZERO writers in
  ``src/``, so every real HMAC row hits its refusal branch while the code
  believes the buyer supplied nothing.
* ``protocol_webhook_service`` compares spec-cased ``"Bearer"`` /
  ``"HMAC-SHA256"`` and reads ``authentication_token`` — the AdCP 3.1.1 field.
* ``webhook_delivery_service`` does a third thing again.

Three copies is not a coincidence; it is what happens when the auth decision is
a two-line ``if`` that is cheaper to retype than to look up. The fix is one
resolver (``webhook_auth_for`` in :mod:`src.core.security.webhook_egress`), and
this guard is what keeps copy #4 from appearing — the same role
``test_architecture_no_hardcoded_unsigned_webhook.py`` plays for the sibling
defect, whose own docstring records that the previous instance was "caught by a
disease scan, not a test failure".

Two shapes are detected, because the disease has two halves and either one
alone is enough to diverge:

**A. Comparing ``authentication_type`` against a scheme literal.** This is where
the SPELLING divergence lives (``"bearer"`` vs ``"Bearer"``). Reading the column
for logging or for a read-back response is fine; deciding from it is not.

**B. Reading ``authentication_token`` / ``webhook_secret`` off another object.**
This is where the FIELD divergence lives. Writes (``x.authentication_token =
...``, ``authentication_token=...`` keyword arguments) are untouched — the
persistence path is not the disease. ``self.<attr>`` is untouched too: an object
reading its own attribute (``WebhookVerifier.webhook_secret``, the RECEIVER-side
verifier) is not a sender picking a column off a stored config.

Scope note — the guard deliberately does NOT try to detect
``src/admin/blueprints/principals.py``'s hand-built ``PushNotificationConfig``
(disposition row 5, deferred to salesagent-qb9q). That site names ``auth_type=``
/ ``auth_config=``, kwargs that are not columns on the model at all; it is a
different defect (it writes nothing that any sender can read) and belongs to its
own ticket. Widening this detector to catch it would mean matching on invented
names, which no rule can state.
"""

from __future__ import annotations

import ast

import pytest

from tests.unit._architecture_helpers import (
    assert_detector_catches_ast_snippets,
    assert_violations_match_allowlist,
    iter_call_expressions,
    parse_module,
    rel,
    repo_root,
    src_python_files,
)

# The scheme spellings a sender may not compare against inline. Both cases are
# listed because the whole point is that the two senders disagree about which
# one the column holds; the resolver is where that comparison becomes
# case-insensitive, and it is the ONLY place allowed to make it.
_SCHEME_LITERALS = frozenset(
    {
        "Bearer",
        "bearer",
        "HMAC-SHA256",
        "hmac-sha256",
        "hmac_sha256",
        "Basic",
        "basic",
    }
)

# Credential columns a sender may not read off a config object.
_CREDENTIAL_ATTRS = frozenset({"authentication_token", "webhook_secret"})

# The resolver's own module — "outside the resolver" is the rule, so the
# resolver is not scanned. Not an allowlist entry: an allowlist records debt,
# and this records the one legitimate home for the logic.
_RESOLVER_MODULE = "src/core/security/webhook_egress.py"

# The one function allowed to be handed the raw columns (see
# ``_resolver_argument_nodes``).
_RESOLVER_FUNCTION = "webhook_auth_for"

# Files permitted to still contain the disease, by path. Shrink-only.
#
# Two kinds of entry, and they are documented differently at the source:
#
# * DEBT — the disease is really there and someone will remove it. Needs a
#   ``# FIXME(#<gh-issue>)`` comment at the source location (a GitHub issue, never
#   a beads id, so an outside contributor can resolve it). Closing the issue
#   removes the entry.
# * JUSTIFIED FALSE POSITIVE — the detector matches but the semantic is different,
#   and there is nothing to fix. A FIXME would be a lie about future work; the
#   reason lives in the comment here and beside the code.
#
# This guard grades the file SET; the source comments tell the next reader which
# kind each one is.
_ALLOWLIST: set[tuple] = {
    # ``src/services/webhook_delivery_service.py`` was here until
    # salesagent-47n9.24 (GH #1894) converged it on the resolver. Do not re-add
    # it, or anything else: the only remaining entry below is a justified false
    # positive, so a NEW debt entry would mean a sender started resolving auth
    # inline again -- which is the whole disease.
    #
    # Justified false positive: ``on_get_task_push_notification_config`` and the
    # config LIST response read ``config.authentication_token`` to echo the
    # buyer's own registration back to them. That is a read-BACK, not a sender
    # deciding how to authenticate an outbound request — the resolver has
    # nothing to offer it.
    ("src/a2a_server/adcp_a2a_server.py",),
}

_FIX_HINT = (
    "Resolve webhook auth through src.core.security.webhook_egress.webhook_auth_for(scheme, credentials) "
    "and match on the returned WebhookAuth variant. Do not compare authentication_type against a scheme "
    "literal, and do not read authentication_token/webhook_secret off a config at the call site — that is "
    "how three senders ended up with three different answers."
)


def _is_scheme_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in _SCHEME_LITERALS


def _names_authentication_type(node: ast.expr) -> bool:
    """True for ``x.authentication_type`` or a bare ``authentication_type``."""
    if isinstance(node, ast.Attribute):
        return node.attr == "authentication_type"
    return isinstance(node, ast.Name) and node.id == "authentication_type"


def _is_self(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def _credential_read_lineno(node: ast.AST) -> int | None:
    """Line number if *node* reads a credential column off another object."""
    if isinstance(node, ast.Attribute):
        reads_credential = node.attr in _CREDENTIAL_ATTRS and isinstance(node.ctx, ast.Load)
        if reads_credential and not _is_self(node.value):
            return node.lineno
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
        # getattr(config, "webhook_secret", None) — the duck-typed spelling of
        # the same read, and the one webhook_delivery_service actually uses.
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            if node.args[1].value in _CREDENTIAL_ATTRS and not _is_self(node.args[0]):
                return node.lineno
    return None


def _resolver_argument_nodes(tree: ast.AST) -> set[int]:
    """``id()`` of every expression handed straight to the resolver.

    The resolver takes PRIMITIVES, so a migrated sender necessarily writes
    ``webhook_auth_for(config.authentication_type, config.authentication_token)``
    — that read is the fix, not the disease, and flagging it would make the
    rule unsatisfiable. Only a read passed DIRECTLY to the resolver is exempt:
    stashing the column in a local first and using it elsewhere is exactly the
    inline resolution this guard exists to stop.
    """
    exempt: set[int] = set()
    for node in iter_call_expressions(tree, _RESOLVER_FUNCTION):
        for arg in node.args:
            exempt.add(id(arg))
        for keyword in node.keywords:
            exempt.add(id(keyword.value))
    return exempt


def find_inline_webhook_auth_violations(tree: ast.Module) -> list[int]:
    """Return line numbers where webhook auth is resolved inline."""
    violations: list[int] = []
    exempt = _resolver_argument_nodes(tree)
    for node in ast.walk(tree):
        if id(node) in exempt:
            continue
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            names_column = any(_names_authentication_type(operand) for operand in operands)
            names_literal = any(_is_scheme_literal(operand) for operand in operands)
            if names_column and names_literal:
                violations.append(node.lineno)
                continue
        lineno = _credential_read_lineno(node)
        if lineno is not None:
            violations.append(lineno)
    return sorted(violations)


def _violating_src_files() -> dict[str, list[int]]:
    repo = repo_root()
    found: dict[str, list[int]] = {}
    for path in src_python_files(repo):
        relpath = rel(path)
        if relpath == _RESOLVER_MODULE:
            continue
        lines = find_inline_webhook_auth_violations(parse_module(path))
        if lines:
            found[relpath] = lines
    return found


class TestNoInlineWebhookAuthResolution:
    """(a) Real ``src/`` — only the deferred rows may still resolve auth inline."""

    def test_src_matches_allowlist(self) -> None:
        found = _violating_src_files()
        assert_violations_match_allowlist(
            {(relpath,) for relpath in found},
            _ALLOWLIST,
            fix_hint=f"{_FIX_HINT}\n\nViolating lines: {found}",
        )


class TestDetectorCatchesKnownBadSnippets:
    """(b) Positive meta-tests — every inline-resolution shape is caught."""

    def test_catches_known_bad_snippets(self) -> None:
        assert_detector_catches_ast_snippets(
            find_inline_webhook_auth_violations,
            snippets={
                "compare-lowercase-bearer": 'if config.authentication_type == "bearer":\n    pass\n',
                "compare-spec-cased-bearer": 'if config.authentication_type == "Bearer":\n    pass\n',
                "compare-hmac": 'if cfg.authentication_type == "HMAC-SHA256":\n    pass\n',
                "compare-literal-on-the-left": 'if "HMAC-SHA256" == cfg.authentication_type:\n    pass\n',
                "compare-bare-name": 'if authentication_type == "Bearer":\n    pass\n',
                "read-authentication-token": "token = config.authentication_token\n",
                "read-webhook-secret": "secret = config.webhook_secret\n",
                "getattr-webhook-secret": 'secret = getattr(config, "webhook_secret", None)\n',
                "f-string-credential-read": 'headers["Authorization"] = f"Bearer {config.authentication_token}"\n',
            },
        )


class TestDetectorAllowsCleanSnippets:
    """(c) Negative meta-tests — persistence, logging and read-back stay legal."""

    @pytest.mark.parametrize(
        ("label", "snippet"),
        [
            ("resolver-call", "auth = webhook_auth_for(config.authentication_type, config.authentication_token)\n"),
            ("keyword-write", "repo.upsert(authentication_type=auth_type, authentication_token=credentials)\n"),
            ("attribute-write", "existing.authentication_token = authentication_token\n"),
            ("secret-write", "existing.webhook_secret = webhook_secret\n"),
            ("own-attribute-read", "digest = hmac.new(self.webhook_secret.encode())\n"),
            ("log-the-scheme", 'logger.info("scheme=%s", config.authentication_type)\n'),
            ("compare-against-a-variable", "if config.authentication_type == expected_scheme:\n    pass\n"),
            ("compare-against-non-scheme-literal", 'if config.authentication_type == "none":\n    pass\n'),
            ("unrelated-attribute", "url = config.url\n"),
        ],
    )
    def test_allows_clean_snippet(self, label: str, snippet: str) -> None:
        tree = ast.parse(snippet, filename=f"<known-good:{label}>")
        assert not find_inline_webhook_auth_violations(tree), f"detector false-flagged clean snippet: {label}"
