"""The Admin advertiser summary: a GAM report's rows summed per line item and per order.

``GAMReportingService.get_advertiser_summary`` groups the report with
``ReportingData.sum_by``. The service is the real one over a stand-in GAM client whose
report job finishes with the rows below (``gam_reporting_service``).
"""

from __future__ import annotations

import pytest

from tests.helpers.gam_client import gam_delivery_row, gam_reporting_service

pytestmark = pytest.mark.unit


def _row(
    order: tuple[str, str], line_item: tuple[str, str], date: str, impressions: int, clicks: int, spend: float
) -> dict[str, object]:
    """One report row for a line item of an order, each given as ``(id, name)``."""
    return {
        **gam_delivery_row(
            advertiser_id="501",
            order_id=order[0],
            line_item_id=line_item[0],
            impressions=impressions,
            spend=spend,
            date=date,
        ),
        "Dimension.ORDER_NAME": order[1],
        "Dimension.LINE_ITEM_NAME": line_item[1],
        "Column.AD_SERVER_CLICKS": clicks,
    }


def test_summary_sums_each_line_item_and_each_order():
    """Two orders, three line items, one of them reported on two days.

    A line item's rows are summed into one entry that names its order; an order's entry
    sums its line items and counts them. Both lists are in the order the service's rows
    first name them: by day, then by spend, highest first.
    """
    order_a, order_b = ("9001", "Order A"), ("9002", "Order B")
    rows = [
        _row(order_a, ("7001", "A, first"), "2025-01-14", impressions=1000, clicks=10, spend=5.0),
        _row(order_b, ("7003", "B, only"), "2025-01-14", impressions=200, clicks=2, spend=1.0),
        _row(order_a, ("7002", "A, second"), "2025-01-14", impressions=300, clicks=3, spend=1.5),
        _row(order_a, ("7001", "A, first"), "2025-01-15", impressions=500, clicks=5, spend=2.5),
    ]

    with gam_reporting_service(rows=rows) as service:
        summary = service.get_advertiser_summary("501", "this_month")

    assert summary["line_items"] == [
        {
            "line_item_id": "7001",
            "line_item_name": "A, first",
            "order_id": "9001",
            "order_name": "Order A",
            "impressions": 1500,
            "clicks": 15,
            "spend": 7.5,
        },
        {
            "line_item_id": "7002",
            "line_item_name": "A, second",
            "order_id": "9001",
            "order_name": "Order A",
            "impressions": 300,
            "clicks": 3,
            "spend": 1.5,
        },
        {
            "line_item_id": "7003",
            "line_item_name": "B, only",
            "order_id": "9002",
            "order_name": "Order B",
            "impressions": 200,
            "clicks": 2,
            "spend": 1.0,
        },
    ]
    assert summary["orders"] == [
        {
            "order_id": "9001",
            "order_name": "Order A",
            "impressions": 1800,
            "clicks": 18,
            "spend": 9.0,
            "line_item_count": 2,
        },
        {
            "order_id": "9002",
            "order_name": "Order B",
            "impressions": 200,
            "clicks": 2,
            "spend": 1.0,
            "line_item_count": 1,
        },
    ]
    assert summary["advertiser_id"] == "501"
    assert summary["date_range"] == "this_month"
