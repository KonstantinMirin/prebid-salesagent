"""Domain step definitions for BR-SECURITY-001 (salesagent-prkv.8 / prkv.18).

Formalizes, as a Gherkin scenario graded across a2a/mcp/rest (+ e2e-REST), the
obligation that an untyped exception raised inside a dispatched skill's
business logic never puts its own text on the buyer-facing wire.
AdCP 3.1.1 dist/docs/3.1.1/building/implementation/transport-errors.mdx,
Security Considerations MUST-NOT list.

Given: "a tenant is configured for product discovery" is reused from
    tests/bdd/steps/domain/uc_get_products_inventory.py (already registered
    as a pytest-bdd step by that module) — not redefined here.
When: dispatch_request(ctx, ...) — the ONE sanctioned writer of ctx["result"].
Then: TWO assertions, both required (neither alone closes the gap) —
    positively pins the observation to the injected fault via
    assert_wire_error(..., message_substr=type(exc).__name__), and negatively
    asserts the fault's own (plainly-internal-looking) marker text is absent
    from the FULL wire envelope via assert_no_marker_in_envelope.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from tests.bdd.steps.generic._dispatch import dispatch_request
from tests.helpers import assert_no_marker_in_envelope

# A distinctive, plainly-internal-looking payload (a fake DSN) — if this
# string appears anywhere in the wire envelope, the raw exception leaked.
# Mirrors tests/integration/test_prkv8_untyped_exception_wire_leak.py's
# _SECRET_MARKER technique.
_FAKE_DSN_MARKER = "postgres://admin:s3cr3t-security001@10.0.0.9:5432/prod_shadow"


class _InjectedUntypedFault(RuntimeError):
    """Distinctively-named untyped exception injected by this scenario.

    Not a bare RuntimeError: production's normalize_to_adcp_error() fallback
    emits ``type(exc).__name__`` as the wire-safe message, so this class name
    becomes the positive assertion target — pinning the observation to THIS
    injected fault specifically (any unrelated unhandled exception would not
    match the class-name substring), which is what kills the vacuity risk
    flagged in architect review.
    """


# ── Given steps ─────────────────────────────────────────────────────


@given("an untyped exception is raised inside the dispatched skill's business logic")
def given_untyped_exception(ctx: dict) -> None:
    """Force the dispatched skill's business logic to raise an untyped fault.

    Delegates to the shared harness capability (BaseTestEnv.inject_untyped_exception)
    rather than a per-scenario mock.patch, so the same Given works unmodified
    across a2a/mcp/rest (and e2e-REST, where it declares itself unsupported).
    """
    env = ctx["env"]
    env.inject_untyped_exception(_InjectedUntypedFault(_FAKE_DSN_MARKER))


# ── When steps ──────────────────────────────────────────────────────


@when("the Buyer Agent requests products")
def when_buyer_agent_requests_products(ctx: dict) -> None:
    """Dispatch get_products through the current transport."""
    dispatch_request(ctx, brief="video ads")


# ── Then steps ──────────────────────────────────────────────────────


@then(parsers.parse('the response is an error with code "{code}" and no raw exception text'))
def then_safe_wire_envelope(ctx: dict, code: str) -> None:
    """Assert the wire envelope is buyer-safe: the right code AND no leaked text.

    Positive: pins the observation to the injected fault via message_substr
    (production emits type(exc).__name__ per normalize_to_adcp_error).
    Negative: scans the FULL envelope (not just errors[0].message) for the
    fault's own internal-looking marker text — a leak anywhere in the
    envelope (adcp_error.message, errors[0].details, suggestion, context)
    fails this check.
    """
    result = ctx["result"]
    result.assert_wire_error(
        code,
        recovery="transient",
        message_substr=_InjectedUntypedFault.__name__,
    )
    assert_no_marker_in_envelope(result.wire_error_envelope, _FAKE_DSN_MARKER)
