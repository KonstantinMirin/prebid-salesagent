"""BDD binding for the locally-added GAM delivery-report feature.

Grades that get_media_buy_delivery, served by the REAL Google Ad Manager adapter, reports a
buy GAM has no report rows for with zero delivery, and a report GAM failed to produce as an
error for that buy (get_media_buy_delivery.mdx, AdCP 3.1.1).

Local rather than BR-UC-004: the storyboard scenario injects the adapter's answer, so the
adapter's own reading of an empty report is graded only here.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-delivery-report.feature")
