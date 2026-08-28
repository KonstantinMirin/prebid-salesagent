"""Exception-hierarchy behavior that has no other grader in this suite.

Everything this module once asserted about a code's ``message``, ``recovery`` or
``suggestion`` is gone: all three are read-only properties over ``CODE_TABLE``
(``src/core/errors/codes.py``, built at import from the pinned adcp SDK's own
enums), so pinning them per exception class copies the pinned table into a
second place instead of grading production. The "class code is in the
vocabulary" checks are gone for the same reason inverted:
``AdCPSalesAgentError.__init_subclass__`` raises ``TypeError`` at class-creation
time for a ``_code`` the table does not classify, so a violating class cannot be
constructed for a test to catch. The wire-code translation suite is gone with
the symbols it exercised (``ERROR_CODE_MAPPING``, ``translate_error_code``,
``to_dict``, ``to_adcp_error``, ``wire_error_code``): the AdCP error vocabulary
is open, codes now reach the buyer verbatim, and the envelope has one builder.

What remains is behavior that lives in *code* rather than in the table, and that
nothing else in the suite exercises:

- The per-class HTTP ``status_code``. It is the one graded wire-adjacent value
  ``CODE_TABLE`` does not carry, so no table-derivation argument covers it.
  ``tests/unit/test_error_boundary_translation.py::TestRestStatusCodeRoundtrip``
  grades that the value survives the REST handler stack; graded here is the
  distinct obligation that each class *declares* the status the roundtrip then
  carries — including the classes that roundtrip does not drive.
- ``AdCPSalesAgentError.iter_concrete_subclasses()``. Its only production
  consumer is ``_build_error_code_to_status`` in
  ``src/core/tool_error_logging.py``, which iterates it but pins none of the
  walk's promises: transitive, deduplicated across diamond inheritance, never
  yielding ``cls`` itself, skipping abstract bases.
- The ``context`` echo surviving the REST exception handler and reaching the
  response body. The BDD lines that would grade it have no step definition and
  are converted to xfail by ``tests/bdd/conftest.py``, so no scenario reaches
  it.

Retry-after on both envelope layers, the IDEMPOTENCY_* code/recovery pairs, and
the two-layer envelope shape itself are all graded elsewhere (respectively
``tests/helpers/envelope_assertions.py::assert_envelope_shape`` +
``tests/integration/test_idempotency_rate_limit.py``,
``tests/integration/test_idempotency_replay.py`` and the BR-UC-003 feature, and
every BDD error scenario), so they are not restated here.
"""

from __future__ import annotations

import abc

import pytest
from starlette.testclient import TestClient

from src.core.errors.codes import AppErrorCode
from src.core.exceptions import (
    AdCPAdapterError,
    AdCPAuthenticationError,
    AdCPAuthorizationError,
    AdCPBudgetExhaustedError,
    AdCPConflictError,
    AdCPGoneError,
    AdCPProductNotFoundError,
    AdCPRateLimitError,
    AdCPSalesAgentError,
    AdCPServiceUnavailableError,
    AdCPValidationError,
)

# ---------------------------------------------------------------------------
# HTTP status is the one graded value CODE_TABLE does not own
# ---------------------------------------------------------------------------


class TestPerClassHttpStatus:
    """Each typed class declares the HTTP status its raise sites mean.

    ``status_code`` is not a function of the error code — the table classifies
    message, recovery and suggestion, and stops there — so it is the one
    per-class value a test can pin without transcribing the pin. Two readers
    depend on the declaration: ``src/app.py``'s handler stack (``exc.status_code``
    becomes the response status) and ``_build_error_code_to_status``, which reads
    the ``_default_status_code`` class slot to answer for plain-``ToolError``
    fallbacks that carry no typed exception.
    """

    @pytest.mark.parametrize(
        ("exc_cls", "expected_status"),
        [
            (AdCPAuthenticationError, 401),
            (AdCPAuthorizationError, 403),
            (AdCPConflictError, 409),
            (AdCPGoneError, 410),
            (AdCPBudgetExhaustedError, 422),
            (AdCPRateLimitError, 429),
            (AdCPAdapterError, 502),
            (AdCPServiceUnavailableError, 503),
        ],
        ids=lambda value: value.__name__ if isinstance(value, type) else str(value),
    )
    def test_class_declares_its_status(self, exc_cls: type[AdCPSalesAgentError], expected_status: int):
        """A new typed subclass is one parametrize row, not one method."""
        assert exc_cls().status_code == expected_status

    def test_base_defaults_to_500(self):
        """The base carries 500: an error that names no class-specific status is a
        server fault, not a buyer-correctable one.
        """
        exc = AdCPSalesAgentError(error_code=AppErrorCode.INTERNAL_ERROR)

        assert exc.status_code == 500


# ---------------------------------------------------------------------------
# The subclass walk behind the wire-code -> HTTP-status table
# ---------------------------------------------------------------------------


class TestIterConcreteSubclasses:
    """Lock the contract of ``AdCPSalesAgentError.iter_concrete_subclasses()``.

    ``_build_error_code_to_status`` depends on this walk visiting every
    transitive subclass exactly once; it iterates the generator but pins none of
    its behavior, so a regression in transitivity, dedup or self-exclusion would
    silently produce a table missing rows or overwriting them.
    """

    def test_yields_transitive_descendants_once_excluding_cls(self):
        """Generic walk: transitive, deduplicated across diamonds, never yields cls."""
        # Exercise the underlying function with a local root so the real subclass
        # tree stays untouched — subclassing AdCPSalesAgentError here would leak
        # these throwaway classes into every other test that enumerates it (and
        # each would have to declare a CODE_TABLE code to be creatable at all).
        walk = AdCPSalesAgentError.iter_concrete_subclasses.__func__

        class _Base: ...

        class _Mid(_Base): ...

        class _Leaf(_Mid): ...

        class _Other(_Base): ...

        class _Diamond(_Mid, _Other): ...  # reachable via both _Mid and _Other

        result = list(walk(_Base))

        # Transitive: the grandchild (_Leaf) and the diamond are reached, not
        # just the direct children.
        assert set(result) == {_Mid, _Leaf, _Other, _Diamond}
        # Deduplicated despite two parent paths to _Diamond.
        assert result.count(_Diamond) == 1
        # Never yields the class it was called on.
        assert _Base not in result

    def test_real_tree_is_transitive_and_excludes_base(self):
        """On the real hierarchy: a two-level-deep subclass is yielded, the base is not."""
        concrete = set(AdCPSalesAgentError.iter_concrete_subclasses())

        # AdCPSalesAgentError -> AdCPNotFoundError -> AdCPProductNotFoundError.
        assert AdCPProductNotFoundError in concrete
        assert AdCPSalesAgentError not in concrete

    def test_skips_abstract_bases_yields_concrete_descendants(self):
        """Abstract bases are walked through but not yielded — the 'concrete' promise."""
        walk = AdCPSalesAgentError.iter_concrete_subclasses.__func__

        class _Root: ...

        class _AbstractMid(_Root, abc.ABC):
            @abc.abstractmethod
            def handle(self) -> None: ...

        class _Concrete(_AbstractMid):
            def handle(self) -> None: ...

        result = list(walk(_Root))

        assert _Concrete in result  # concrete descendant of an abstract base is yielded
        assert _AbstractMid not in result  # the abstract base itself is skipped


# ---------------------------------------------------------------------------
# context echo through the REST exception handler
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def context_echo_client() -> TestClient:
    """A minimal app wired to the PRODUCTION ``AdCPSalesAgentError`` handler.

    The handler object registered here is ``src.app.adcp_error_handler`` itself,
    so what is graded is production's envelope path (``_envelope_response`` ->
    ``build_two_layer_error_envelope``) and not a second copy of it. The app is
    dedicated rather than ``src.app.app`` so the test is ordering-independent:
    with pytest-randomly the global app may already have admin catch-all mounts
    installed via lifespan, which would swallow a route added after startup.
    """
    from fastapi import FastAPI

    from src.app import adcp_error_handler

    app = FastAPI()
    app.add_exception_handler(AdCPSalesAgentError, adcp_error_handler)

    @app.get("/raise/with-context")
    def raise_with_context() -> None:
        from adcp.types import ContextObject

        raise AdCPValidationError(context=ContextObject(correlation_id="trace-xyz"))

    return TestClient(app, raise_server_exceptions=False)


class TestErrorEnvelopeContextEcho:
    """The envelope echoes the raise site's ``ContextObject`` (AdCP 3.1.1 normative).

    Buyer agents correlate a failure back to the request that produced it through
    this key. The BDD lines that would grade it bind to no step definition and
    are routed to xfail by ``tests/bdd/conftest.py``, so this is the only place
    the echo is exercised end to end.
    """

    def test_context_is_echoed_in_the_http_response(self, context_echo_client: TestClient):
        """A ``ContextObject`` on the exception reaches the response body serialized.

        Graded at the HTTP boundary rather than on ``build_two_layer_error_envelope``:
        the builder's own echo (including the omit-when-absent rule) is pinned in
        ``tests/unit/test_error_envelope.py::TestContextEcho``. What only the
        handler can lose is the key on the way out.
        """
        response = context_echo_client.get("/raise/with-context")

        assert response.status_code == 400
        assert response.json()["context"] == {"correlation_id": "trace-xyz"}
