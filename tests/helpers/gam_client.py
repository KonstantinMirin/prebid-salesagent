"""Stand-ins for the GAM SOAP client, for tests that drive the GAM adapter.

The adapter has no dry-run mode: every read and write it makes is a GAM call. It used
to fabricate its own test data when ``dry_run`` was set — ``_get_line_item_info``
returned a line item map naming "mock_package" / "package_1" / "test_package" with
invented ``creativePlaceholders`` — so the creative-size check compared a test's
creative against sizes production itself made up.

That branch is STILL PRESENT in ``src/adapters/gam/managers/creatives.py`` (the ``else``
of ``if line_item_service:``); only the ``dry_run`` half of its guard was removed, and
GH #2245 tracks deleting it. It is unreachable — ``add_creative_assets`` always passes
the service it just asked the client manager for — so nothing here may depend on it: a
test that needs a line item states one.
"""

from __future__ import annotations

import csv
import gzip
import io
import itertools
from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock


class SoapObject(dict):
    """A GAM (Zeep) object stand-in: production reads these by key AND by attribute."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def gam_line_item(name: str, *, item_id: str = "1001", sizes: tuple[tuple[int, int], ...] = ((728, 90),)) -> SoapObject:
    """One line item in a GAM order, carrying the creative sizes it accepts."""
    return SoapObject(
        name=name,
        id=item_id,
        creativePlaceholders=[
            SoapObject(size=SoapObject(width=width, height=height), creativeSizeType="PIXEL") for width, height in sizes
        ],
    )


def stub_gam_client_manager(
    *,
    line_items: tuple[SoapObject, ...] | list[SoapObject] = (),
    created_creative_id: str = "gam_creative_1",
    created_order_id: str = "9000001",
    created_line_item_id: str = "9100001",
    network_time_zone: str = "America/New_York",
) -> MagicMock:
    """A ``GAMClientManager`` instance stand-in serving the order's line items.

    Every service the adapter asks for resolves: the ones a test states behaviour for
    are configured, and any other is a bare mock so a call reaching it neither fails
    nor pretends to have done anything.

    ``createOrders`` and ``createLineItems`` answer with NUMERIC ids because production
    reads them back and converts: ``create_order`` does ``str(created[0]["id"])`` and the
    approval path then does ``int(order_id)``. A bare mock satisfies the subscript (every
    MagicMock does) and yields ``"<MagicMock ...>"``, which fails much later as
    ``invalid literal for int()`` -- a create that never touched a real client looking
    like an ad-server fault.

    ``getCurrentNetwork`` names the network's time zone, the zone production writes a
    line item's flight in.

    Each line item GAM creates gets its own id, counting up from ``created_line_item_id``
    in creation order and recorded by line item name on ``line_item_ids``, so a buy's
    packages map to distinct line items the way they do on a real network. A line item
    it created is then one of the order's line items, as GAM serves them back.
    """
    next_line_item_id = itertools.count(int(created_line_item_id))
    line_item_ids: dict[str, str] = {}
    order_line_items = list(line_items)

    def create_line_items(items: list[dict[str, Any]]) -> list[dict[str, int]]:
        created = [{"id": next(next_line_item_id)} for _ in items]
        for item, row in zip(items, created, strict=True):
            line_item_ids[item["name"]] = str(row["id"])
            order_line_items.append(SoapObject(item, id=row["id"]))
        return created

    services = {
        "NetworkService": MagicMock(getCurrentNetwork=MagicMock(return_value=SoapObject(timeZone=network_time_zone))),
        "OrderService": MagicMock(createOrders=MagicMock(return_value=[{"id": int(created_order_id)}])),
        "LineItemService": MagicMock(
            getLineItemsByStatement=MagicMock(side_effect=lambda _statement: SoapObject(results=order_line_items)),
            createLineItems=MagicMock(side_effect=create_line_items),
        ),
        "CreativeService": MagicMock(createCreatives=MagicMock(return_value=[{"id": created_creative_id}])),
        # Stated so the associations a test grades land on ONE object: an unstated
        # service resolves to a fresh mock per lookup, which records nothing readable.
        "LineItemCreativeAssociationService": MagicMock(),
    }
    client_manager = MagicMock()
    # setdefault, not ``or MagicMock()``: every ask for a service gets the SAME stand-in,
    # so a call on one nobody configured (LineItemCreativeAssociationService, ...) is
    # still recorded where a test can read it back.
    client_manager.get_service.side_effect = lambda name: services.setdefault(name, MagicMock())
    client_manager.line_item_ids = line_item_ids
    return client_manager


#: Where GAM's ``getReportDownloadURL`` points: a host the reporting service's provenance
#: check accepts (``ReportingConfig.ALLOWED_DOMAINS``).
GAM_REPORT_DOWNLOAD_URL = "https://storage.googleapis.com/gam-report.csv.gz"


def serve_gam_report(client_manager: MagicMock, *, status: str = "COMPLETED") -> None:
    """Give *client_manager*'s SOAP client a ReportService whose job ends in *status*.

    ``GAMReportingService`` talks to the SOAP client the adapter holds
    (``client_manager.get_client()``), not to ``get_service``: it runs the job, polls its
    status, and asks for the CSV's download URL. A ``FAILED`` job is the report failure the
    seller must still surface. The CSV itself is fetched over HTTP -- see
    ``gam_report_download``.
    """
    report_service = MagicMock(
        runReportJob=MagicMock(return_value={"id": 7001}),
        getReportJobStatus=MagicMock(return_value=status),
        getReportDownloadURL=MagicMock(return_value=GAM_REPORT_DOWNLOAD_URL),
    )
    network_service = MagicMock(getCurrentNetwork=MagicMock(return_value=SoapObject(timeZone="America/New_York")))
    services = {"ReportService": report_service, "NetworkService": network_service}
    client_manager.get_client.return_value.GetService.side_effect = lambda name, *a, **kw: (
        services.get(name) or MagicMock()
    )


#: The columns of the report ``GAMReportingService`` asks GAM for, as GAM's CSV names them.
_GAM_REPORT_COLUMNS = (
    "Dimension.DATE",
    "Dimension.ADVERTISER_ID",
    "Dimension.ORDER_ID",
    "Dimension.LINE_ITEM_ID",
    "Column.AD_SERVER_IMPRESSIONS",
    "Column.AD_SERVER_CLICKS",
    "Column.AD_SERVER_CPM_AND_CPC_REVENUE",
)


def gam_report_download(rows: Iterable[dict[str, Any]] = ()) -> MagicMock:
    """The HTTP response carrying a GAM report: a gzipped CSV of *rows*, keyed by GAM column.

    With no rows it is a header-only CSV, a report that ran and found no delivery.
    ``Column.AD_SERVER_CPM_AND_CPC_REVENUE`` is in micros, as GAM reports it.
    """
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=_GAM_REPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return MagicMock(content=gzip.compress(text.getvalue().encode()))
