"""Deciding WHICH constraint an ``IntegrityError`` violated.

A unique index is the only real defence against two concurrent writers, so the
loser of a race necessarily takes an ``IntegrityError``. Recovering from it is
routine; recovering from the WRONG one is not. An unnarrowed
``except IntegrityError`` swallows foreign-key, CHECK and primary-key violations
too and reports them as whatever collision the handler happened to expect, which
turns a real defect into a misleading success (see the caveats recorded on
``src/admin/blueprints/public.py``'s recovery, #1721).

This module is the one place that answers "is this error THAT constraint?", so a
handler states the constraint it recovers from and everything else propagates.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def is_constraint_violation(
    exc: IntegrityError,
    constraint: str,
    *,
    message_token: str | None = None,
) -> bool:
    """True iff ``exc`` is a violation of ``constraint``.

    Prefers the driver's structured constraint name
    (``exc.orig.diag.constraint_name``), matched by PREFIX — so a build-time
    rename suffix (e.g. the ``CREATE INDEX CONCURRENTLY`` swap variants) still
    matches, while an unrelated constraint that merely contains the same column
    token does not.

    Falls back to a substring scan of the driver message only when the structured
    diagnostic is unavailable (non-psycopg2 drivers, wrapped errors).
    ``message_token`` overrides what that fallback looks for; it defaults to the
    constraint name.
    """
    name = getattr(getattr(exc, "orig", None), "diag", None)
    constraint_name = getattr(name, "constraint_name", None)
    if constraint_name:
        return constraint_name.startswith(constraint)
    return (message_token or constraint) in str(getattr(exc, "orig", exc))
