"""BDD binding for the locally-added GAM line-item booking feature.

Grades the line item the seller books in Google Ad Manager for each package: a goal its
own budget buys at its own price, labelled with a goal type GAM allows for the line item
type, at the product's configured priority when GAM allows it.

Local rather than a BR-* storyboard: AdCP is silent on how a seller traffics a package.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-line-item-booking.feature")
