"""BDD binding for the locally-added GAM buy read-back feature.

Grades what a buyer reads back about a buy created through a Google Ad Manager seller:
its status once its inline creatives are approved and attached, and each package's
delivery under the package's own id, price and GAM-reported spend.

Local rather than a BR-* storyboard: no storyboard creates through a GAM seller.
"""

from __future__ import annotations

from pytest_bdd import scenarios

# The get_media_buys poll and its status Then are UC-019's, which registers its steps at
# module scope (see test_uc019_query_media_buys.py); importing them here binds them to
# this feature the same way.
from tests.bdd.steps.domain.uc019_query_media_buys import *  # noqa: F401,F403,E402

scenarios("features/local-gam-buy-readback.feature")
