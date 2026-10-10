"""Steps for local-gam-line-item-flight.feature.

The tenant is made a Google Ad Manager seller through the env
(``MediaBuyCreateEnv.sell_through_gam``): production's ``get_adapter`` builds the real
``GoogleAdManager`` adapter and only GAM's SOAP client is a stand-in. The oracle is the
line item the seller sent that client — the ad server is where a flight's instants are
observable, and the buyer's wire response does not echo them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pytest_bdd import given, parsers, then


@given(parsers.parse('the tenant sells through Google Ad Manager on a network in time zone "{time_zone}"'))
def given_tenant_sells_through_gam(ctx: dict, time_zone: str) -> None:
    ctx["env"].sell_through_gam(ctx["tenant"], ctx["principal"], ctx["default_product"], network_time_zone=time_zone)


def _gam_datetime(wall_clock: str, time_zone: str) -> dict[str, Any]:
    """The GAM DateTime naming ``wall_clock`` (a zone-less ISO 8601 time) in ``time_zone``."""
    local = datetime.fromisoformat(wall_clock)
    return {
        "date": {"year": local.year, "month": local.month, "day": local.day},
        "hour": local.hour,
        "minute": local.minute,
        "second": local.second,
        "timeZoneId": time_zone,
    }


def _only_line_item(ctx: dict) -> dict[str, Any]:
    line_items = ctx["env"].gam_line_items_sent()
    assert len(line_items) == 1, f"Expected one line item sent to GAM, got {len(line_items)}"
    return line_items[0]


@then(parsers.parse('GAM receives a line item starting {start} and ending {end} in time zone "{time_zone}"'))
def then_gam_line_item_flight(ctx: dict, start: str, end: str, time_zone: str) -> None:
    line_item = _only_line_item(ctx)
    flight = {key: line_item.get(key) for key in ("startDateTimeType", "startDateTime", "endDateTime")}
    if start == "immediately":
        expected = {"startDateTimeType": "IMMEDIATELY", "startDateTime": None}
    else:
        expected = {"startDateTimeType": None, "startDateTime": _gam_datetime(start, time_zone)}
    expected["endDateTime"] = _gam_datetime(end, time_zone)
    assert flight == expected, f"GAM line item flight {flight} != {expected}"
