"""BDD scenario binding for UC-008: Manage Audience Signals (get_signals).

Uses pytest-bdd's ``scenarios()`` to auto-generate test functions from the
generated feature file. Step definitions are imported via conftest.py.

Wired set (#1594): main-rest and main-context-echo pass against the exposed
get_signals surface; main-mcp is wired but strict-xfailed on two production
gaps — a natural-language signal_spec matches nothing, because production
substring-matches the whole phrase (#1600), and the signal catalog carries
no value_type (#1593); see conftest _SPEC_GAP_XFAILS. activate_signal
scenarios stay dormant: the tool is deliberately unregistered until
v3.1.1-conformant (#1593).
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/BR-UC-008-manage-audience-signals.feature")
