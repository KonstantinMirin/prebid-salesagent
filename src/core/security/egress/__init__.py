"""The egress policy package: one address predicate, shared by every verdict
that decides whether this application dials a URL, and one retry state
machine shared by every attempt loop.

``policy.py`` (Epic A lane 1) and ``attempts.py`` (lane 2) exist today. A
sibling lane still to land adds ``response.py`` (the closed ``OutboundResult``
shape) — see ``.claude/notes/pr1802-r2-class-fix-plan.md``.
"""
