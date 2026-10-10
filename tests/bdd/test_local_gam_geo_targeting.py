"""BDD binding for the locally-added GAM geo-targeting feature.

Grades that a package's geo overlay reaches the line item the Google Ad Manager
adapter sends to GAM, and that a geo code with no GAM location is refused before
anything is booked. The pinned authority is named in the feature's header.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-geo-targeting.feature")
