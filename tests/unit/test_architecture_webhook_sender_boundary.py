"""Guard: every outbound AdCP webhook SENDER goes through the one signing boundary.

#1291 C1 (``salesagent-z6nr.18``), design step 6, last bullet — and the reason it
is written this way is a measured hole, not a style preference:

    A guard counting ``sign_webhook`` call sites passes with five senders and two
    routed. That hole is exactly what let ``order_approval_service`` exist as a
    fourth, unsigned AdCP webhook sender for as long as it did (salesagent-98t2) —
    nobody was counting SENDERS.

So this guard enumerates senders. It AST-discovers every outbound HTTP POST in
``src/`` whose destination is DYNAMIC (a name or attribute, not a literal or
f-string — i.e. a URL somebody else supplied rather than a fixed API path), and
requires every one of them to be classified in one of the three tables below. A
new POST to a caller-supplied URL anywhere in ``src/`` therefore fails this guard
until someone states which kind it is.

Of the three kinds, only :data:`ADCP_WEBHOOK_SENDERS` is subject to the boundary
rule: those destinations come from a buyer's own registration (a
``PushNotificationConfig`` row, an account notification subscriber, or the mock
adapter's async-completion URL), so what they carry is an AdCP webhook and the
receiver's registration selects how it is authenticated. When C1 routes a sender
through ``adcp.webhooks.WebhookSender``, its hand-rolled POST DISAPPEARS — the
sender stops being discovered here at all. That is the pass condition, and it is
not fakeable by adding a call somewhere in the module: the raw POST has to go.

``ALLOWED_UNROUTED`` therefore holds only the senders C1 does NOT own, each of
which must carry a ``FIXME(#1291)`` at its source location so the debt is visible
where the code is, not only in this table. Per the repository's allowlist rule,
it can only shrink.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit._architecture_helpers import assert_violations_match_allowlist

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

#: The GitHub issue every allowlisted sender must reference at its source location.
#: A beads id would not resolve for an outside contributor, so it is never used here.
FIXME_MARKER = "FIXME(#1291)"

#: Destinations that are a THIRD-PARTY API this agent calls, not a webhook it emits.
#: Nothing about AdCP webhook signing applies to them.
AD_SERVER_AND_API_CALLS: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/adapters/broadstreet/client.py", "url"),
        ("src/adapters/xandr.py", "auth_url"),
        ("src/adapters/xandr.py", "url"),
        ("src/core/creative_agent_registry.py", "mcp_url"),
    }
)

#: Destinations that ARE outbound webhooks but whose receiver is not an AdCP buyer.
#: Slack is the only one; it must never be sent an RFC 9421 signature, so routing it
#: through the AdCP boundary would be a defect rather than a fix.
NON_ADCP_RECEIVERS: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/adapters/base_workflow.py", "slack_webhook_url"),
        ("src/admin/blueprints/tenants.py", "tenant.slack_webhook_url"),
        ("src/core/webhook_delivery.py", "delivery.webhook_url"),
    }
)

#: The AdCP webhook senders. Every one of these POSTs to a URL a buyer registered,
#: so every one of them must be authenticated by the mode that buyer's registration
#: selects — which is what the single boundary decides.
ADCP_WEBHOOK_SENDERS: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/services/protocol_webhook_service.py", "url"),
        ("src/services/webhook_delivery_service.py", "config.url"),
        ("src/services/order_approval_service.py", "webhook_url"),
        ("src/services/notification_proof_service.py", "url"),
        ("src/adapters/mock_ad_server.py", "self.async_webhook_url"),
    }
)

#: AdCP senders C1 does NOT route, each with the ticket that will. Only shrinks.
ALLOWED_UNROUTED: frozenset[tuple[str, str]] = frozenset(
    {
        # C2 (salesagent-z6nr.19) — the proof-of-control challenge MUST be signed;
        # C1 shapes the boundary so C2 can call it.
        ("src/services/notification_proof_service.py", "url"),
        # salesagent-hop4 — the mock adapter's task_completed notification. Same
        # registration-derived destination, same missing signature.
        ("src/adapters/mock_ad_server.py", "self.async_webhook_url"),
    }
)

CLASSIFIED = AD_SERVER_AND_API_CALLS | NON_ADCP_RECEIVERS | ADCP_WEBHOOK_SENDERS


def _destination(call: ast.Call) -> ast.expr | None:
    """The URL argument of a ``.post()`` / ``.request()`` call, if it has one."""
    if call.args:
        # ``requests.request(method, url)`` puts the URL second; every other form
        # here puts it first.
        index = 1 if isinstance(call.func, ast.Attribute) and call.func.attr == "request" and len(call.args) > 1 else 0
        return call.args[index]
    for keyword in call.keywords:
        if keyword.arg == "url":
            return keyword.value
    return None


def _dynamic_post_sites() -> list[tuple[str, str, int]]:
    """(relative path, destination expression, line) for every dynamic-URL POST in src/.

    A literal or f-string destination is a fixed endpoint this agent calls; only a
    bare name or attribute can be a URL someone else registered, which is what makes
    a call site a candidate webhook sender.
    """
    sites: list[tuple[str, str, int]] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in f"/{rel}":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("post", "request"):
                continue
            destination = _destination(node)
            if destination is None or isinstance(destination, (ast.Constant, ast.JoinedStr)):
                continue
            sites.append((rel, ast.unparse(destination), node.lineno))
    return sites


def _enclosing_function_source(rel_path: str, lineno: int) -> str:
    """The source of the function containing *lineno*, for the FIXME check.

    Scoped to the function rather than the file so a ``FIXME(#1291)`` written about
    something else elsewhere in the module cannot silence this one.
    """
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, rel_path)
    lines = text.splitlines()
    best: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            if node.lineno <= lineno <= end and (best is None or node.lineno > best[0]):
                best = (node.lineno, end)
    if best is None:
        return text
    return "\n".join(lines[best[0] - 1 : best[1]])


@pytest.mark.arch_guard
class TestOutboundWebhookSenderBoundary:
    """Senders are enumerated, and the AdCP ones go through one boundary."""

    def test_every_dynamic_destination_post_is_classified(self):
        """A new POST to a caller-supplied URL must be classified before it ships.

        This is the half that makes the guard an ENUMERATION: a sixth outbound
        webhook sender is a build failure the moment it is written, whether or not
        anyone remembers this file exists.
        """
        unclassified = sorted({(rel, expr) for rel, expr, _ in _dynamic_post_sites()} - CLASSIFIED)

        assert not unclassified, (
            "Unclassified outbound POST to a caller-supplied URL:\n"
            + "\n".join(f"  {rel}  ->  {expr}" for rel, expr in unclassified)
            + "\n\nAdd it to exactly one table in this file: AD_SERVER_AND_API_CALLS (a third-party "
            "API this agent calls), NON_ADCP_RECEIVERS (an outbound webhook to a non-AdCP receiver, "
            "e.g. Slack), or ADCP_WEBHOOK_SENDERS (a webhook to a URL a buyer registered — which must "
            "then go through the single signing boundary)."
        )

    def test_every_adcp_webhook_sender_goes_through_the_boundary(self):
        """No AdCP sender hand-rolls its own POST, and the allowlist has no stale rows.

        Routing a sender through ``adcp.webhooks.WebhookSender`` removes its raw
        POST, so a routed sender is simply absent from the discovered set. Anything
        still present is still hand-rolled — and anything allowlisted but absent is
        an entry someone forgot to delete when they fixed it. Both directions are
        the same equality, so they are asserted by the shared helper rather than by
        two hand-rolled set diffs.
        """
        discovered = {(rel, expr) for rel, expr, _ in _dynamic_post_sites()}

        assert_violations_match_allowlist(
            discovered & ADCP_WEBHOOK_SENDERS,
            set(ALLOWED_UNROUTED),
            fix_hint=(
                "Each of these POSTs to a URL a buyer registered, so the buyer's registration must "
                "select the authentication mode (security.mdx @ v3.1.1 :1424). Build the sender with "
                "src.core.signing.webhook_sender_factory.build_webhook_sender and deliver through it; "
                "the hand-rolled POST goes away, and the entry leaves ALLOWED_UNROUTED with it."
            ),
        )

    def test_allowlisted_senders_carry_the_fixme_at_the_source(self):
        """An allowlisted sender says so where it lives, referencing the GH issue.

        A table entry alone is invisible to whoever next reads the sender. The
        marker is a GitHub issue rather than a beads id because beads ids do not
        resolve for outside contributors.
        """
        missing = [
            (rel, expr, lineno)
            for rel, expr, lineno in _dynamic_post_sites()
            if (rel, expr) in ALLOWED_UNROUTED and FIXME_MARKER not in _enclosing_function_source(rel, lineno)
        ]

        assert not missing, (
            f"Allowlisted webhook senders with no {FIXME_MARKER} comment in the sending function:\n"
            + "\n".join(f"  {rel}:{lineno}  ->  {expr}" for rel, expr, lineno in missing)
        )
