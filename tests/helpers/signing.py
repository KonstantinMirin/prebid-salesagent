"""Test helpers for the inbound RFC 9421 verifier.

One helper so far, and it exists because the verifier's DEFAULT is on. A seller that runs
the verifier is a seller that "supports request signing", and security.mdx @ v3.1.1 :1465
then makes a 9421 signature MANDATORY on any request carrying webhook credentials —
``push_notification_config.authentication`` or ``accounts[].notification_configs[]
.authentication`` — regardless of ``required_for`` membership. That is a real production
obligation with its own tests.

It is not, however, the obligation a test about SERIALIZATION or FORWARDING is grading, and
such a test that happens to carry an ``authentication`` block would otherwise be refused
before its subject ran. Those tests say so explicitly, here, rather than quietly dropping
the block their assertions are about.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def verifier_disabled() -> Iterator[None]:
    """Run the block with inbound signature verification off, as the kill switch does.

    Patches the live settings object rather than the environment, because the settings are
    read once and cached: an env var set inside a test is read only if something drops the
    cache first, and a helper that depends on that ordering breaks silently when a caller
    resolves the settings earlier than it expected.
    """
    from src.core.config import get_settings

    signing = get_settings().signing
    previous = signing.verifier_enabled
    signing.verifier_enabled = False
    try:
        yield
    finally:
        signing.verifier_enabled = previous
