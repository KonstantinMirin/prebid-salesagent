"""BDD binding for the locally-added unreported-package delivery feature.

Grades what get_media_buy_delivery reports for a package the ad server did not report:
zero, never a share of the buy, and a buy's only package carrying the buy's delivery.
Graded on a2a, mcp, rest and e2e_rest.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-uc004-unreported-package.feature")
