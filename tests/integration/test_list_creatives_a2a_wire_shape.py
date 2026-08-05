"""A2A wire shape for list_creatives: format_id must stay a {agent_url, id} object.

Regression for GH #1710-adjacent finding (salesagent PR #1868 review, "A2A list_creatives
format_id serializes as bare string instead of {agent_url, id} object"): the pinned AdCP
spec (3.1, core/format-id.json) types every ``format_id`` as a structured object
(``{agent_url, id}``, the v3.1 format-id federation contract) -- never a bare string.

Root cause (traced via ``_reconstruct_response_object`` in
``src/a2a_server/adcp_a2a_server.py``): the A2A explicit-skill success path calls
``self._serialize_for_a2a(result)`` first, producing a correctly-nested
``artifact_data`` dict (``creatives[i].format_id`` is a plain ``{agent_url, id}``
dict at this point). It then calls
``self._reconstruct_response_object(skill_name, artifact_data)`` -- passing the SAME
dict by reference -- purely to generate a human-readable ``__str__()`` text part.
``_reconstruct_response_object`` does ``ListCreativesResponse(**artifact_data)``:
pydantic-core validates the ``creatives: list[Creative]`` field by handing each list
item's dict to ``Creative``'s ``@model_validator(mode="before")``
(``validate_format_id``) WITHOUT a defensive copy -- and that validator does
``values["format_id"] = upgrade_legacy_format_id(format_val)``, MUTATING the shared
dict in place: ``artifact_data["creatives"][i]["format_id"]`` becomes a live
``FormatId`` Python object.

The task/artifact construction that follows (``Part(data=_dict_to_value(artifact_data))``)
now hands ``_dict_to_value`` a dict containing a live, non-JSON-native object.
``_dict_to_value``'s ``json.dumps(d, default=str)`` fallback silently stringifies it:
``FormatId.__str__`` returns ``self.id`` -- exactly the observed bare-string symptom.

This reproduces deterministically with a single creative (not scale-dependent at the
mechanism level) via the real in-process A2A pipeline
(``AdCPRequestHandler.on_message_send`` -> explicit skill dispatch ->
``_serialize_for_a2a`` -> ``_reconstruct_response_object`` -> ``_dict_to_value``),
exercised end-to-end by the harness's ``_run_a2a_handler``.
"""

from __future__ import annotations

import pytest

from tests.factories.core import TenantFactory
from tests.factories.creative import CreativeFactory
from tests.factories.principal import PrincipalFactory
from tests.harness.creative_list import CreativeListEnv
from tests.harness.transport import Transport
from tests.helpers.pinned_schema import validate_against_pinned_schema

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


def _list_creatives_via_a2a(count: int):
    with CreativeListEnv() as env:
        tenant = TenantFactory(tenant_id="test_tenant")
        principal = PrincipalFactory(tenant=tenant, principal_id="test_principal")
        for i in range(count):
            CreativeFactory(tenant=tenant, principal=principal, creative_id=f"cr_a2a_wire_{i:03d}")
        result = env.call_via(Transport.A2A, limit=50)
    assert result.is_success, f"Expected success but got error: {result.error}"
    wire = result.wire_response
    assert wire is not None, "A2A dispatch must stash the real artifact DataPart wire"
    return wire


def test_a2a_wire_format_id_is_object_not_string(integration_db):
    """Every creative's format_id on the real A2A wire is a {agent_url, id} object.

    Mutation check: revert the ``Creative.validate_format_id`` defensive-copy fix
    (make it mutate its input ``values`` dict again) -> this test goes red, with
    format_id observed as a bare string.
    """
    wire = _list_creatives_via_a2a(count=1)
    creatives = wire.get("creatives")
    assert isinstance(creatives, list) and creatives, f"A2A wire must carry the creatives array, got {creatives!r}"
    for i, item in enumerate(creatives):
        format_id = item.get("format_id")
        assert isinstance(format_id, dict), (
            f"creatives[{i}].format_id must be a {{agent_url, id}} object on the A2A wire "
            f"(spec 3.1 core/format-id.json types it object), got {format_id!r} "
            f"(type {type(format_id).__name__})"
        )
        assert "agent_url" in format_id and "id" in format_id, (
            f"creatives[{i}].format_id object is missing agent_url/id: {format_id!r}"
        )


def test_a2a_wire_format_id_object_survives_with_many_creatives(integration_db):
    """Same assertion at a larger creative count -- the original report's reproduction scale."""
    wire = _list_creatives_via_a2a(count=15)
    creatives = wire.get("creatives")
    assert isinstance(creatives, list) and len(creatives) == 15
    for i, item in enumerate(creatives):
        format_id = item.get("format_id")
        assert isinstance(format_id, dict), (
            f"creatives[{i}].format_id must be a {{agent_url, id}} object, got {format_id!r} "
            f"(type {type(format_id).__name__})"
        )


def test_a2a_wire_validates_against_pinned_response_schema(integration_db):
    """The A2A list_creatives wire validates against the pinned list-creatives-response.json."""
    wire = _list_creatives_via_a2a(count=3)
    # Strip the A2A envelope fields (message, success) that _serialize_for_a2a adds --
    # not declared on the ListCreativesResponse payload model.
    payload = {k: v for k, v in wire.items() if k not in ("message", "success")}
    validate_against_pinned_schema("list-creatives-response.json", payload)
