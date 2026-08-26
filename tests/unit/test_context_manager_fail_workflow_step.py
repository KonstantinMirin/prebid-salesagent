"""Unit tests for ``ContextManager.audit_workflow_step_failure``.

Validates the two contracts the helper exists to enforce:

1. Webhook subscribers see the same wire shape as synchronous callers —
   ``response_data`` carries the full two-layer envelope (``adcp_error`` + ``errors[]``),
   not just an opaque ``error_message`` string. Without this, async push
   notifications fire with empty bodies (see ``_send_push_notifications`` at
   ``context_manager.py:715-726``).

2. A DB hiccup during the audit write must NOT shadow the original
   exception. The caller's bare ``raise`` (intended to re-raise the original
   AdCPError) would otherwise pick up the audit-failure exception and the
   buyer would see an unrelated DB error in place of the real validation
   failure.
"""

from unittest.mock import MagicMock

import pytest

from src.core.context_manager import ContextManager
from src.core.errors.details import ValidationDetails
from src.core.exceptions import AdCPError, AdCPValidationError


def _new_ctx_manager_with_mocked_update() -> tuple[ContextManager, MagicMock]:
    """Build a ContextManager instance with ``update_workflow_step`` mocked.

    The helper under test calls ``self.update_workflow_step``; mocking that
    method directly isolates the helper's logic from DB plumbing while still
    exercising real envelope-builder integration.
    """
    cm = ContextManager.__new__(ContextManager)  # bypass __init__ DB setup
    cm.update_workflow_step = MagicMock()  # type: ignore[method-assign]
    return cm, cm.update_workflow_step


def _expected_response_data(exc: AdCPError) -> dict:
    """Build the two-layer wire-shape ``response_data`` the helper must emit.

    Built from the SAME exception the test raises, through the same
    ``build_two_layer_error_envelope`` production calls — so the assertion is on the
    dict ``update_workflow_step`` receives, with nothing reconstructed.

    Reconstructing an equivalent error here would not be equivalent: a NAMED-code
    ``AdCPError`` resolves recovery and suggestion from CODE_TABLE, while a class-coded
    subclass keeps its class defaults. Passing the real exception sidesteps that
    asymmetry instead of encoding it.
    """
    from src.core.exceptions import build_two_layer_error_envelope

    return build_two_layer_error_envelope(exc)


def _normalized_for(exc: Exception) -> AdCPError:
    """The typed error production derives from an untyped one, via the same helper."""
    from src.core.exceptions import adcp_error_for

    return adcp_error_for(exc)


class TestFailWorkflowStepForExceptionWebhookPayload:
    """Webhook subscribers must receive the two-layer envelope, not just error_message."""

    def test_adcp_error_threads_envelope_into_response_data(self):
        cm, mock_update = _new_ctx_manager_with_mocked_update()
        exc = AdCPValidationError(
            field="packages[].budget",
            details=ValidationDetails(reasons=["below minimum"]),
        )

        cm.audit_workflow_step_failure("step_abc", exc)

        # Helper must call update_workflow_step with the exact wire-shape
        # payload subscribers will read off the webhook. Single
        # ``assert_called_once_with`` (no inspection) keeps the test atomic
        # and rejects any future drift in the helper's emitted shape.
        mock_update.assert_called_once_with(
            "step_abc",
            status="failed",
            error_message=exc.message,
            response_data=_expected_response_data(exc),
        )

    def test_untyped_exception_wrapped_with_wire_safe_code(self):
        """Bare exceptions get a synthetic AdCPError so the wire code stays standard.

        ``AdCPError`` defaults to ``INTERNAL_ERROR`` which is in
        ``INTERNAL_CODES``; the helper's defensive wire-code enforcement
        falls back to ``SERVICE_UNAVAILABLE`` so async subscribers only see
        codes from ``STANDARD_ERROR_CODES`` even when the source was untyped.
        Recovery is transient — the pinned enumMetadata classification of the
        SERVICE_UNAVAILABLE wire code (salesagent-nr2q).

        This ``response_data`` is a PERSISTED record (exceptions.py's
        ``build_two_layer_error_envelope`` docstring: "wire responses and
        persisted workflow_step.response_data share the same two-layer
        shape"), read back by async webhook subscribers — so it gets the
        SAME provenance protection prkv.8 gives the live transports:
        ``adcp_error_for()``'s untyped-Exception fallback uses
        ``type(exc).__name__``, never the exception's own ``str()``, which
        has no guarantee of being safe to persist/replay to a subscriber
        (a DSN, a stack fragment, an upstream response body).
        """
        cm, mock_update = _new_ctx_manager_with_mocked_update()

        cm.audit_workflow_step_failure("step_abc", RuntimeError("postgres://admin:s3cr3t@10.0.0.5/prod"))

        # The raw DSN must not reach the payload: the helper normalizes to a typed error
        # whose text comes from the code, so the expected envelope is built the same way.
        expected = _normalized_for(RuntimeError("postgres://admin:s3cr3t@10.0.0.5/prod"))
        mock_update.assert_called_once_with(
            "step_abc",
            status="failed",
            error_message=expected.message,
            response_data=_expected_response_data(expected),
        )
        assert "s3cr3t" not in str(mock_update.call_args)

    def test_untyped_exception_with_no_text_is_indistinguishable(self):
        """A text-less untyped exception yields the same payload as any other.

        Its wording used to be the exception's type name; the sentence is now the
        code's, so an empty ``str(exc)`` is no longer a distinct case at all.
        """
        cm, mock_update = _new_ctx_manager_with_mocked_update()

        cm.audit_workflow_step_failure("step_abc", RuntimeError())

        expected = _normalized_for(RuntimeError())
        mock_update.assert_called_once_with(
            "step_abc",
            status="failed",
            error_message=expected.message,
            response_data=_expected_response_data(expected),
        )


class TestFailWorkflowStepForExceptionAuditFailureNonFatal:
    """A DB hiccup during the audit write must NOT shadow the original exception."""

    def test_update_workflow_step_raise_is_swallowed(self, caplog):
        """If ``update_workflow_step`` raises, the helper logs and returns normally.

        The caller's bare ``raise`` after this helper returns must propagate
        the original exception. Python's exception chaining would otherwise
        replace it with the audit-failure exception, hiding the real error
        from the buyer.
        """
        cm = ContextManager.__new__(ContextManager)
        cm.update_workflow_step = MagicMock(side_effect=RuntimeError("DB went away"))  # type: ignore[method-assign]
        original = AdCPValidationError()

        # Helper must return normally so the caller's `raise` propagates `original`.
        cm.audit_workflow_step_failure("step_abc", original)

        # Audit failure must be logged so SREs can correlate, but the caller
        # never knows it happened — original exception will be re-raised.
        assert any("Failed to audit workflow_step" in record.message for record in caplog.records)

    def test_caller_can_safely_re_raise_after_audit_failure(self):
        """End-to-end: simulate the caller's ``raise`` pattern and verify
        the ORIGINAL exception reaches the test boundary, not the audit one.
        """
        cm = ContextManager.__new__(ContextManager)
        cm.update_workflow_step = MagicMock(side_effect=RuntimeError("DB went away"))  # type: ignore[method-assign]
        original = AdCPValidationError()

        def caller_pattern():
            try:
                # Simulate the body raising
                raise original
            except AdCPValidationError as e:
                cm.audit_workflow_step_failure("step_abc", e)
                raise

        with pytest.raises(AdCPValidationError) as excinfo:
            caller_pattern()
        # The buyer sees the real error, not the audit failure.
        assert excinfo.value is original
