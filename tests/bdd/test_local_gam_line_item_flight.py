"""BDD binding for the locally-added GAM line item flight feature.

Grades that the instants a buyer names on create_media_buy reach GAM as the
network's wall clock labelled with the network's zone.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-gam-line-item-flight.feature")
