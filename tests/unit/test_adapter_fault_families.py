"""An adapter fault reaches the buyer with the code its CONDITION earned.

48 raise sites under ``src/adapters/`` used to raise builtins, so
``adcp_error_for`` classified them by PYTHON TYPE rather than by fault:
``ValueError`` became ``AdCPValidationError`` (VALIDATION_ERROR, "your request is
malformed") for failures entirely on the seller's side, and
``Exception``/``RuntimeError`` fell through to INTERNAL_ERROR or a tool's
catch-all. A missing ``advertiser_id``, an expired credential and a GAM report
job that never finished all read the same way to a buyer: as their own mistake.

ONE ROW PER FAULT FAMILY, not one per site (salesagent-7et3j acceptance 3). 48
tests for 48 sites would grade the copy-paste. What actually varies across the
sites is which of six CONDITIONS holds, and each condition has exactly one right
answer — so six rows are the contract and the rest are repetitions of it.

Each row drives REAL adapter code to its raise, never a hand-constructed
exception: the thing under test is the classification the site performs, and
constructing the class here would assert only that Python can build it.

WIRE CARRIAGE IS GRADED ELSEWHERE, deliberately, rather than duplicated here.
``tests/integration/test_adapter_error_wire_classification.py`` pins that a typed
adapter error survives the tool layer with its own code across mcp/a2a/rest,
through the ``except AdCPError: raise`` arms. That test plus this one compose:
this says the adapter names the right code, that one says nothing rewrites it.

A NOTE ON WHAT IS *NOT* ROWED HERE, so its absence is not read as an oversight.
``gam_reporting_service._run_report`` wraps its whole body in an
``except Exception`` that relabels anything untyped ``AdCPAdapterError``. Every
site inside it therefore ALREADY produced that class through the wrapper, so a
row exercising one of them cannot tell site-level typing apart from
wrapper-level typing. Those conversions are defensive -- they matter when the
function is refactored, or to a caller that catches deeper -- and the thing that
makes the OTHER classes in that function observable is the
``except AdCPError: raise`` arm added alongside them, which
``test_architecture_no_error_flattening`` pins directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import (
    AdCPAdapterError,
    AdCPCapabilityNotSupportedError,
    AdCPConfigurationError,
    AdCPInternalError,
    AdCPValidationError,
)


def _seller_config_missing_credentials():
    """F1: no authentication method configured at all."""
    from src.adapters.gam.auth import GAMAuthManager

    return lambda: GAMAuthManager({})


def _seller_config_missing_network_code():
    """F1: the GAM client cannot be built without a network code."""
    from src.adapters.gam.client import GAMClientManager

    manager = GAMClientManager({"refresh_token": "tok"}, network_code="")
    return manager.get_client


def _unknown_adapter_type():
    """F1: a tenant naming an ad server this build does not ship."""
    from src.adapters import get_adapter_class

    return lambda: get_adapter_class("not_a_real_ad_server")


def _upstream_report_never_completed():
    """F2/F3: GAM accepted the report job and then did not finish it."""
    from src.adapters.gam_reporting_service import GAMReportingService

    service = GAMReportingService.__new__(GAMReportingService)
    report_service = MagicMock()
    report_service.getReportJobStatus.return_value = "FAILED"
    service.report_service = report_service
    service.client = MagicMock()
    return lambda: service._run_report({})


def _capability_the_seller_cannot_offer():
    """F4: a GAM constraint the buyer cannot satisfy by rewording the request."""
    from src.adapters.gam.pricing_compatibility import PricingCompatibility

    return lambda: PricingCompatibility.select_line_item_type(
        pricing_model="flat_rate", is_guaranteed=True, override_type="PRICE_PRIORITY"
    )


def _programming_error():
    """F7: an internal contract the seller broke, about neither buyer nor upstream."""
    from src.adapters.xandr import XandrAdapter

    # Called unbound with a stand-in self. XandrAdapter is abstract and its four
    # unimplemented methods are irrelevant to the branch under test; building a
    # concrete stub would add scaffolding that grades nothing.
    return lambda: XandrAdapter._make_request(MagicMock(), "TRACE", "/whatever")


_FAMILIES = [
    pytest.param(
        _seller_config_missing_credentials, AdCPConfigurationError, "CONFIGURATION_ERROR", id="F1_credentials"
    ),
    pytest.param(
        _seller_config_missing_network_code, AdCPConfigurationError, "CONFIGURATION_ERROR", id="F1_network_code"
    ),
    pytest.param(_unknown_adapter_type, AdCPConfigurationError, "CONFIGURATION_ERROR", id="F1_unknown_adapter"),
    pytest.param(_upstream_report_never_completed, AdCPAdapterError, "SERVICE_UNAVAILABLE", id="F2_upstream_failure"),
    pytest.param(
        _capability_the_seller_cannot_offer, AdCPCapabilityNotSupportedError, "UNSUPPORTED_FEATURE", id="F4_capability"
    ),
    pytest.param(_programming_error, AdCPInternalError, "INTERNAL_ERROR", id="F7_internal"),
]


@pytest.mark.parametrize("build,expected_class,expected_code", _FAMILIES)
def test_fault_family_names_its_own_code(build, expected_class, expected_code) -> None:
    """The raise site classifies by CONDITION, so no fault borrows another's code."""
    call = build()

    with pytest.raises(expected_class) as exc_info:
        call()

    assert exc_info.value.error_code == expected_code

    # The regression this whole ticket exists to prevent, asserted directly rather
    # than implied: none of these is the buyer's fault, so none may arrive as
    # VALIDATION_ERROR. Before the conversion every ValueError-raising site did.
    assert not isinstance(exc_info.value, AdCPValidationError)
    assert exc_info.value.error_code != "VALIDATION_ERROR"


def test_no_converted_site_carries_upstream_text_in_message() -> None:
    """Acceptance 2, and it holds by CONSTRUCTION rather than by inspection.

    ``AdCPError.__init__`` is keyword-only and has no ``message`` parameter, so a
    raise site cannot interpolate an upstream exception's text into the
    buyer-facing sentence — not "should not", cannot. The sentence is a function
    of the code through ``CODE_TABLE``; provenance rides ``internal_detail``,
    which the transport boundary logs server-side and never puts on the wire.
    """
    with pytest.raises(TypeError, match="positional argument"):
        AdCPAdapterError("Failed to create order: <SOAP fault text>")  # type: ignore[call-arg]


def test_pydantic_field_validators_still_raise_value_error() -> None:
    """Acceptance 4: the 8 excluded sites must NOT have been converted.

    Inside a pydantic field validator, ``ValueError`` IS the contract — pydantic
    converts it to a ``ValidationError``, and VALIDATION_ERROR is then the
    correct buyer code because the value really did come from the request.
    Converting them would have been a regression, so this test would fail if a
    future sweep "finished the job".
    """
    from src.adapters.gam_implementation_config_schema import GAMImplementationConfig

    with pytest.raises(ValueError, match="Invalid line_item_type"):
        GAMImplementationConfig.validate_line_item_type("NOT_A_GAM_LINE_ITEM_TYPE")
