"""The Admin advertiser summary: a GAM report's rows summed per line item and per order.

``GAMReportingService.get_advertiser_summary`` groups the report with
``ReportingData.sum_by``. The service is the real one over a stand-in GAM client whose
report job finishes with the rows below (``gam_reporting_service``).
"""

from __future__ import annotations

import pytest

from tests.helpers.gam_client import gam_delivery_row, gam_reporting_service

pytestmark = pytest.mark.unit


def _row(order_id: str, line_item_id: str, date: str, impressions: int, clicks: int, spend: float) -> dict[str, object]:
    """One report row for a line item of an order, in the columns the summary's query requests."""
    return {
        **gam_delivery_row(
            advertiser_id="501",
            order_id=order_id,
            line_item_id=line_item_id,
            impressions=impressions,
            spend=spend,
            date=date,
        ),
        "Column.AD_SERVER_CLICKS": clicks,
    }


def _without_names(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """*entries* without ``order_name`` and ``line_item_name``, which the summary's report cannot fill (#2421)."""
    return [{key: value for key, value in entry.items() if not key.endswith("_name")} for entry in entries]


def test_summary_sums_each_line_item_and_each_order():
    """Two orders, three line items, one of them reported on two days.

    A line item's rows are summed into one entry that names its order's id; an order's
    entry sums its line items and counts them. Both lists are in the order the service's
    rows first name them: by day, then by spend, highest first. The names are not compared:
    the summary's dated query requests ids only, so its report has no name columns (#2421).
    """
    rows = [
        _row("9001", "7001", "2025-01-14", impressions=1000, clicks=10, spend=5.0),
        _row("9002", "7003", "2025-01-14", impressions=200, clicks=2, spend=1.0),
        _row("9001", "7002", "2025-01-14", impressions=300, clicks=3, spend=1.5),
        _row("9001", "7001", "2025-01-15", impressions=500, clicks=5, spend=2.5),
    ]

    with gam_reporting_service(rows=rows) as service:
        summary = service.get_advertiser_summary("501", "this_month")

    assert _without_names(summary["line_items"]) == [
        {"line_item_id": "7001", "order_id": "9001", "impressions": 1500, "clicks": 15, "spend": 7.5},
        {"line_item_id": "7002", "order_id": "9001", "impressions": 300, "clicks": 3, "spend": 1.5},
        {"line_item_id": "7003", "order_id": "9002", "impressions": 200, "clicks": 2, "spend": 1.0},
    ]
    assert _without_names(summary["orders"]) == [
        {"order_id": "9001", "impressions": 1800, "clicks": 18, "spend": 9.0, "line_item_count": 2},
        {"order_id": "9002", "impressions": 200, "clicks": 2, "spend": 1.0, "line_item_count": 1},
    ]
    assert summary["advertiser_id"] == "501"
    assert summary["date_range"] == "this_month"
