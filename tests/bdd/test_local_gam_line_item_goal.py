"""BDD binding for the locally-added Google Ad Manager line item goal feature.

Grades the type, priority and goal of each line item a GAM seller books: each package's
volume from its own budget at its selected option's price, on the create path and on the
seller's approval; the goal units following the goal type the line item type admits; and
the product's configured type and priority, honoured or refused before the order exists.
The real GoogleAdManager adapter runs, with only Google's SOAP client stood in
(``GamSellerMixin.sell_through_gam``). Graded on a2a, mcp and rest.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-line-item-goal.feature")
