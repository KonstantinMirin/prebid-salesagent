"""Browser tests for shipped static assets that need NO running server.

``tests/ui/conftest.py`` seeds the server's database and enables test auth for
every test in the ui suite. Tests here drive a shipped asset (a JS file loaded
into a blank page via ``add_script_tag``) and never talk to the app, so that
setup does not apply -- and inheriting it would make them SKIP whenever the
Docker stack is absent, turning a regression gate into a silent no-op.

The overrides below shadow the parent fixtures by name so these tests run
anywhere Playwright is installed, including a bare local checkout.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_auth_enabled():
    """No-op override: these tests never authenticate against the app."""
    return None


@pytest.fixture(scope="session")
def base_url():
    """No-op override: these tests never navigate to the app.

    Returns None (the pytest-base-url default) rather than the parent's
    ``http://<stack-host>:<port>``, so the parent's Docker-stack host lookup is
    never triggered here. This fixture cannot simply be omitted: pytest-
    playwright's ``page`` fixture resolves ``base_url`` transitively, so it is
    requested even though no test navigates.
    """
    return None
