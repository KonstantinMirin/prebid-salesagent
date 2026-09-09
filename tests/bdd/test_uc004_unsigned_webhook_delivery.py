"""BDD binding for the locally-added UC-004 unsigned-delivery feature.

BR-UC-004 grades the two signed deliveries and nothing grades the absent
authentication block, which the pinned reporting-webhook schema makes optional.
This is the delivered → never-delivered guard for every buyer who never asked
to be signed.

Retire once adcp-req compiles an authentication-present × authentication-absent
partition into BR-UC-004.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("features/local-uc004-unsigned-webhook-delivery.feature")
