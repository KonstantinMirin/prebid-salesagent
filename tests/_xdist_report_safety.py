"""Keep an unserializable test report from silently voiding an xdist session.

The hole
--------
pytest hands a report to the xdist wire via
``_pytest/reports.py::_report_to_json``, which starts with::

    d = report.__dict__.copy()      # EVERY attribute, raw

and then sanitizes exactly three things: ``longrepr``, values that are
``os.PathLike``, and ``result``. Everything else any plugin has attached to the
report crosses the wire as-is. execnet's ``_Serializer._save`` dispatches on
``type(obj)`` with an EXACT match over
``NoneType bool bytes complex dict float frozenset int list long set str tuple
Channel`` -- a *subclass* of any of those is refused too -- and raises
``DumpError`` for anything else.

A ``DumpError`` on a worker kills the worker; the master then trips its own
assertion (``xdist/dsession.py:232``) or dies with "Unexpectedly no active
workers available". Either way the session ends **after** reporting only the
tests already collected back, and the summary line says zero failures. A
truncated run is indistinguishable from a green one.

The live instance
-----------------
``pytest-json-report`` -- which ``tox.ini`` passes on every suite -- attaches
``report._json_report_extra`` (its ``plugin.py:105``), whose ``['log']`` entry
holds ``dict(record.__dict__)`` for each captured log record
(``plugin.py:51``). That handler nulls ``msg``, ``args`` and ``exc_info``, but
``logging`` merges anything passed as ``extra={...}`` straight into
``record.__dict__``, so an ``extra`` payload reaches the wire untouched.

Production logs that way in ~75 places -- e.g.
``src/adapters/gam/utils/logging.py:386`` (``extra={"details": details}``) --
so a unit test with a mocked collaborator puts a ``MagicMock`` on the wire
without failing, without asserting anything unusual, and without any hint in
its own output. Measured on this branch, ``tests/unit/`` + ``tests/harness/``
with ``--json-report`` and a FIXED order (``-p no:randomly``):

    workers  collected  reported  lost  summary
      0        5846       5846      0   5810 passed, 0 failed
      4        5846       5430    416   5394 passed, 0 failed
      8        5846       5348    498   5312 passed, 0 failed
     14        5846       5271    575   5235 passed, 0 failed

This module closes the hole at the wire boundary rather than at the ~75 call
sites: the boundary is one place and cannot be regressed by new logging, and
the same hole is open to any future plugin attribute, not just this one.

An offender is REPLACED, never dropped, and always announced on stderr with
its report and key path -- the failure mode being fixed here is silence, so
trading a crash for a quiet mutation would miss the point.
"""

from __future__ import annotations

import sys
from typing import Any

# execnet's _Serializer._save does `self._dispatch[type(obj)]` -- an exact type
# match. Subclasses (an IntEnum, a str subclass, a dict subclass) are refused
# exactly like a mock is, so membership is tested with `type(x) is` semantics
# for atoms and normalised to the base type for containers.
_ATOM_TYPES: frozenset[type] = frozenset({type(None), bool, bytes, complex, float, int, str})

# Guards against a pathological structure costing more than the run it protects.
_MAX_DEPTH = 40
_REPR_LIMIT = 240


def _short_repr(value: Any) -> str:
    """``repr`` that cannot itself raise, and cannot blow up the wire payload."""
    try:
        text = repr(value)
    except Exception as exc:  # a __repr__ that raises must not become a second crash
        text = f"<unreprable {type(value).__name__}: {exc!r}>"
    return text if len(text) <= _REPR_LIMIT else text[: _REPR_LIMIT - 3] + "..."


def _type_name(value: Any) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def make_execnet_safe(value: Any, *, _depth: int = 0, _seen: frozenset[int] = frozenset()) -> tuple[Any, list[str]]:
    """Return ``(safe_value, offenders)``.

    ``safe_value`` contains only types execnet serializes. ``offenders`` names
    every value that had to be replaced, as ``"<key path>: <type>"``, so the
    caller can report rather than silently swallow. An empty list means the
    input was already safe and ``safe_value`` is equivalent to it.
    """
    if type(value) in _ATOM_TYPES:
        return value, []

    if _depth >= _MAX_DEPTH:
        return _short_repr(value), [f" = <depth limit {_MAX_DEPTH}> {_type_name(value)}"]

    ident = id(value)
    if ident in _seen:
        return _short_repr(value), [f" = <cycle> {_type_name(value)}"]

    offenders: list[str] = []

    if isinstance(value, dict):
        seen = _seen | {ident}
        out: dict[Any, Any] = {}
        for key, item in value.items():
            safe_key, key_offenders = make_execnet_safe(key, _depth=_depth + 1, _seen=seen)
            safe_item, item_offenders = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            offenders.extend(f"<key>{o}" for o in key_offenders)
            offenders.extend(
                f".{safe_key}{o}" if isinstance(safe_key, str) else f"[{safe_key!r}]{o}" for o in item_offenders
            )
            out[safe_key] = safe_item
        return out, offenders

    if isinstance(value, (list, tuple)):
        seen = _seen | {ident}
        items = []
        for index, item in enumerate(value):
            safe_item, item_offenders = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            offenders.extend(f"[{index}]{o}" for o in item_offenders)
            items.append(safe_item)
        # Normalise subclasses (namedtuples included) to the exact base type.
        return (list(items) if isinstance(value, list) else tuple(items)), offenders

    if isinstance(value, (set, frozenset)):
        seen = _seen | {ident}
        items = []
        for item in value:
            safe_item, item_offenders = make_execnet_safe(item, _depth=_depth + 1, _seen=seen)
            offenders.extend(item_offenders)
            items.append(safe_item)
        base = set if isinstance(value, set) else frozenset
        return base(items), offenders

    # Everything else -- including subclasses of the atom types, which execnet's
    # exact-type dispatch refuses just as firmly as it refuses a mock.
    return _short_repr(value), [f" = {_type_name(value)}"]


def sanitize_serialized_report(data: Any, *, nodeid: str = "<unknown>", stream: Any = None) -> Any:
    """Sanitize one already-serialized report dict, announcing any offender.

    Returns ``data`` unchanged (same object) when nothing had to be replaced, so
    the common path costs one walk and no allocation of a replacement tree.
    """
    if not isinstance(data, dict):
        return data
    safe, offenders = make_execnet_safe(data)
    if not offenders:
        return data
    out = stream if stream is not None else sys.stderr
    print(
        f"[xdist-report-safety] {nodeid}: {len(offenders)} value(s) in this report cannot cross "
        f"the execnet wire and were replaced by their repr -- "
        f"{'; '.join(sorted(set(offenders))[:10])}"
        f"{' ...' if len(set(offenders)) > 10 else ''}",
        file=out,
        flush=True,
    )
    return safe
