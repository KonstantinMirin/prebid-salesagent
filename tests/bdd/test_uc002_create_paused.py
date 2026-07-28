"""BDD binding for the locally-added UC-002 create-in-paused-state feature.

Grades the create half of the AdCP 3.1.1 `paused` request field (GH #1619)
across the wire transports. See the feature file header for the schema citation
and the (ungraded) storyboard finding.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-uc002-create-paused.feature")
