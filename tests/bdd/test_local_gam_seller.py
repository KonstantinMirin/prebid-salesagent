"""BDD binding for the locally-added Google Ad Manager seller feature.

Grades the objects a GAM seller sends Google Ad Manager when a buyer's create_media_buy
succeeds, with the real GoogleAdManager adapter and only Google's SOAP client stood in
(``MediaBuyCreateEnv.sell_through_gam``). Graded on a2a, mcp and rest.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-seller.feature")
