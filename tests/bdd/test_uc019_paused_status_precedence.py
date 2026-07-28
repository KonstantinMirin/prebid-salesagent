"""BDD binding for the locally-added UC-019 paused status-precedence feature.

Grades the READ-surface precedence a paused media buy is reported under
(pending_creatives > pending_start > paused > active) across every transport.
See the feature file header for the v3.1.1 schema citation and the storyboard
(ungraded) finding. GH #1619.
"""

from __future__ import annotations

from pytest_bdd import scenarios

# Register UC-019 step definitions LOCALLY (module scope), same as
# test_uc019_query_media_buys.py: the uc019 module intentionally redefines
# generic step texts, and a global registration would override them for every
# other use case.
from tests.bdd.steps.domain.uc019_query_media_buys import *  # noqa: F401,F403,E402

scenarios("features/local-uc019-paused-status-precedence.feature")
