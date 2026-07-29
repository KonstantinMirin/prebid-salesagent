"""Land a concurrent commit inside a handler's check-then-write window.

A handler that guards a UNIQUE index reads first (pre-check), then writes. In
production the losing request is one whose pre-check ran *before* the winner
committed and whose write lands *after* — it only learns about the conflict from
the index.

Racing two real threads reproduces that but blocks on the index until the winner
commits, which makes the test timing-dependent. This instead fires the
conflicting commit — from an independent session, so it is a genuinely separate
transaction — at the instant the handler reaches its write. Same interleaving,
made deterministic.

Patching only ``get_db_session`` keeps the handler itself untouched: the
pre-check, the row construction, the recovery and the commit are all real
production code.

``trigger`` names the ``Session`` method that marks the write instant, because
that instant is not the same statement at every site:

``"add"``
    The insert sites. ``session.add()`` is called exactly once, strictly after
    the pre-check and strictly before the write reaches the index.
``"begin_nested"``
    Sites whose contested statement is an UPDATE of an already dirty row, which
    never call ``add()``. ``begin_nested()`` is opened by ``resolve_or_write``
    only after the pre-check has answered ``None``, so it is the write window
    itself. ``"flush"`` would not do: autoflush calls it on every earlier query,
    including the pre-check's own, which would commit the winner *before* the
    pre-check reads and grade the fast path instead of the race.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import patch


def operator_answer(client: Any, response: Any) -> tuple[int, str | None, list[Any]]:
    """What the operator actually sees: status, redirect target, flashed messages.

    Four of the six sites answer a duplicate with a 302 or a 200 carrying the
    message in a flash, so "the loser is not a 500" is not an assertion — the
    winner's and the loser's answers have to be equal as a whole. Flashes are
    popped so consecutive requests on one client do not accumulate.
    """
    with client.session_transaction() as sess:
        flashed = list(sess.pop("_flashes", []))
    return response.status_code, response.headers.get("Location"), flashed


@contextmanager
def concurrent_commit_in_write_window(
    module: ModuleType,
    commit_conflicting_row: Callable[[], object],
    *,
    trigger: str = "add",
) -> Iterator[None]:
    """Patch ``module.get_db_session`` so ``commit_conflicting_row`` fires once, mid-write."""
    real_get_db_session = module.get_db_session

    @contextmanager
    def racing_get_db_session():
        with real_get_db_session() as session:
            unbound = getattr(type(session), trigger)
            fired = False

            def racing_method(*args, **kwargs):
                nonlocal fired
                if not fired:
                    fired = True
                    commit_conflicting_row()
                return unbound(session, *args, **kwargs)

            setattr(session, trigger, racing_method)
            try:
                yield session
            finally:
                # Restore the class method on the (pooled, scoped) session.
                delattr(session, trigger)

    with patch.object(module, "get_db_session", racing_get_db_session):
        yield
