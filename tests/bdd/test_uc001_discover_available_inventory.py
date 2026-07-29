"""BDD scenario binding for UC-001: Discover Available Inventory (get_products).

Uses pytest-bdd's ``scenarios()`` to auto-generate test functions from the
generated feature file. Step definitions are imported via conftest.py.

Wired set (#1594): alt-empty and alt-filtered pass on all wire transports.
T-UC-001-main and T-UC-001-alt-anonymous are wired but strict-xfailed on
real production gaps — the wire never carries brief_relevance (#1595), and
the require_identity gate rejects the anonymous public-manifest request
(#1591); see conftest _SPEC_GAP_XFAILS. Every other scenario stays dormant
via the UC-001 fixture catch-all xfail.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/BR-UC-001-discover-available-inventory.feature")
