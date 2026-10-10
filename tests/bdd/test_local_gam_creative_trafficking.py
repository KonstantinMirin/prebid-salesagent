"""BDD binding for the locally-added GAM creative-trafficking feature.

Grades what a GAM seller sends its ad server when a buyer syncs a creative and
assigns it to a live package: the creative GAM is asked to create, and the line item
it is associated with. No storyboard observes a seller's ad server, so the obligation
is local; the feature header cites the pinned schemas it rests on.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-creative-trafficking.feature")
