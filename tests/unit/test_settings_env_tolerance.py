"""The settings loader reads the environment the way the helpers it replaced did.

Two facts, both reproduced as startup crashes on checked-in inputs before they were graded:

- An EMPTY value is an unset value. ``.github/workflows/ci.yml`` sets ``ADCP_TESTING: ""``
  on the e2e host and the compose files use ``${VAR:-}``, so a container gets ``''`` for a
  variable the host left unset. The replaced helpers read ``''`` as the default.
- The six group names are not environment variables. ``Settings`` is a plain composite,
  so a shell with ``TESTING=1`` or ``DATABASE=x`` starts the process.
"""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from src.core.config import Settings, TestingSettings, load_settings


@pytest.mark.parametrize(
    ("name", "read"),
    [
        ("ADCP_TESTING", lambda s: s.testing.adcp_testing),
        ("DB_PORT", lambda s: s.database.db_port),
        ("DELIVERY_WEBHOOK_INTERVAL", lambda s: s.limits.delivery_webhook_interval),
    ],
)
def test_empty_value_is_the_default(monkeypatch: pytest.MonkeyPatch, name: str, read) -> None:
    monkeypatch.delenv(name, raising=False)
    expected = read(load_settings())

    monkeypatch.setenv(name, "")

    assert read(load_settings()) == expected


def test_empty_values_are_the_defaults_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """The acceptance command, as a test: all three empty at once."""
    for name in ("ADCP_TESTING", "DB_PORT", "DELIVERY_WEBHOOK_INTERVAL"):
        monkeypatch.setenv(name, "")

    settings = load_settings()

    assert settings.testing.adcp_testing is False
    assert settings.database.db_port == 5432
    assert settings.limits.delivery_webhook_interval == 3600


def test_group_names_are_not_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("TESTING", "1"),
        ("DATABASE", "x"),
        ("RUNTIME", "y"),
        ("AUTH", "z"),
        ("INTEGRATIONS", "1"),
        ("LIMITS", "2"),
    ):
        monkeypatch.setenv(name, value)

    settings = load_settings()

    assert not issubclass(Settings, BaseSettings)
    assert isinstance(settings.testing, TestingSettings)
