"""The egress policy package: one address predicate, shared by every verdict
that decides whether this application dials a URL.

``policy.py`` is the only module here today (Epic A lane 1). Sibling lanes
add ``attempts.py`` (the retry state machine) and ``response.py`` (the closed
``OutboundResult`` shape) — see ``.claude/notes/pr1802-r2-class-fix-plan.md``.
"""
