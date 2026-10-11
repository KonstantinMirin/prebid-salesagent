"""When the GAM freshness heuristic expects a period's figures complete.

``GAMDataFreshnessValidator.expected_availability`` is a pure function of the report's
metadata, the target date and the clock passed in. The spec defines no value for it
(get-media-buy-delivery-response.json: ``expected_availability`` is "When delayed data is
expected to be available"), and no wire carries it yet: the delivery webhook holds while
the period is unfinished, and a buyer's pull carries no ``expected_availability``. When the
``T-UC-004-status-reporting-delayed``, ``T-UC-004-webhook-partial-data`` and
``T-UC-004-boundary-delayed-data`` scenarios are bound and grade the time on the webhook, this
test is deleted in favour of them.

Each row named for a check is one where only that check fails, so deleting the check fails
the row.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytz

from src.adapters.gam_data_freshness import GAMDataFreshnessValidator
from src.adapters.gam_reporting_service import ReportingData

ET = pytz.timezone("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return ET.localize(datetime(year, month, day, hour, minute, second))


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _report(query_type: str, *, end: datetime, valid_until: datetime) -> ReportingData:
    return ReportingData(
        data=[],
        start_date=end.replace(day=1, hour=0, minute=0, second=0),
        end_date=end,
        requested_timezone="America/New_York",
        data_timezone="America/New_York",
        data_valid_until=valid_until,
        query_type=query_type,
        dimensions=["DATE"],
        metrics={},
    )


@pytest.mark.parametrize(
    ("now", "report", "target", "expected"),
    [
        pytest.param(
            _utc(2025, 1, 15, 17),
            _report("this_month", end=_et(2025, 1, 15, 12), valid_until=_et(2025, 1, 14, 23, 59, 59)),
            _utc(2025, 1, 15, 17),
            _et(2025, 1, 16, 7, 5),
            id="buyer-pull-midday-check-2",
        ),
        pytest.param(
            _utc(2025, 1, 16, 2),
            _report("this_month", end=_et(2025, 1, 15, 21), valid_until=_et(2025, 1, 14, 23, 59, 59)),
            _utc(2025, 1, 16, 2),
            _et(2025, 1, 16, 7, 5),
            id="buyer-pull-evening-target-date-read-in-et-check-2",
        ),
        pytest.param(
            _utc(2025, 1, 15, 8),
            _report("today", end=_et(2025, 1, 15, 3), valid_until=_et(2025, 1, 14, 23)),
            _et(2025, 1, 14, 23, 59),
            _et(2025, 1, 15, 7, 5),
            id="yesterday-before-ready-hour-check-1",
        ),
        pytest.param(
            _utc(2025, 1, 15, 17),
            _report("this_month", end=_et(2025, 1, 15, 12), valid_until=_et(2025, 1, 9, 23, 59, 59)),
            _et(2025, 1, 10, 0),
            _et(2025, 1, 16, 7, 5),
            id="gam-behind-after-target-morning-next-day",
        ),
        pytest.param(
            _utc(2025, 1, 15, 15),
            _report("today", end=_et(2025, 1, 15, 10), valid_until=_et(2025, 1, 15, 6)),
            _utc(2025, 1, 15, 0),
            None,
            id="complete",
        ),
        pytest.param(
            _utc(2025, 1, 15, 12, 5),
            _report("this_month", end=_et(2025, 1, 15, 7, 5), valid_until=_et(2025, 1, 13, 23, 59, 59)),
            _et(2025, 1, 14, 0),
            _et(2025, 1, 15, 7, 5),
            id="completion-time-equal-to-now-is-now",
        ),
        pytest.param(
            _utc(2025, 1, 15, 11),
            _report("this_month", end=_et(2025, 1, 15, 6), valid_until=_et(2025, 1, 13, 23, 59, 59)),
            _et(2025, 1, 10, 0),
            _et(2025, 1, 15, 7, 5),
            id="gam-behind-after-target-morning-same-day",
        ),
        pytest.param(
            _utc(2025, 1, 15, 12, 5),
            _report("this_month", end=_et(2025, 1, 15, 7, 5), valid_until=_et(2025, 1, 9, 23, 59, 59)),
            _et(2025, 1, 10, 0),
            _et(2025, 1, 15, 7, 5),
            id="next-ready-time-equal-to-now-is-now",
        ),
    ],
)
def test_expected_availability(
    now: datetime, report: ReportingData, target: datetime, expected: datetime | None
) -> None:
    assert GAMDataFreshnessValidator.expected_availability(report, target, now=now) == expected
