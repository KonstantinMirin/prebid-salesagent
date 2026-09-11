"""REST API v1 endpoints.

REST transport for AdCP tools, proving the 3-transport pattern
(MCP + A2A + REST). Every route reaches its implementation through
``src.core.tools._boundary.invoke_tool``.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.auth_context import AuthContext, get_auth_context
from src.core.exceptions import AdcpFailure
from src.core.resolved_identity import TransportProtocol
from src.core.tools._announced_shape import apply_signature
from src.core.tools._boundary import serve, wire_status
from src.core.tools._wire import to_wire
from src.core.tools.registry import TOOLS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


# Note: ToolError handling lives entirely in the global ``@app.exception_handler``
# in src/app.py — REST routes never catch ToolError or import the MCP-boundary
# type (AdCPToolError). The wire-code -> HTTP status table moved to
# src/core/tool_error_logging.py alongside handle_tool_error.


# ---------------------------------------------------------------------------------------
# Routes are DERIVED from the registry. There is no @router decorator to write and no body
# model to assign: TOOLS says which tools are reachable over REST, with what verb and at
# what path, and everything else is resolved from the row.
#
# Every row with a ``rest`` binding gets a route. There is no second condition: the handler
# calls ``invoke_tool``, which reaches the implementation through the registry, so a row can
# no longer be reachable over one transport and not another for want of a per-tool wrapper.


def _rest_handler(tool_name: str, spec: Any) -> Any:
    """One route handler, built from a registry row.

    It takes ``Request`` and validates nothing itself. Declaring the DTO as the body
    parameter is what makes FastAPI validate inside its dependency solving, ahead of this
    function -- and ahead of this function is too early, because a rejected request owes the
    buyer its ``context`` back and only ``validated_request`` returns it. MCP already made
    exactly this trade, and for the same reason: ``RegistryTool`` subclasses ``Tool`` rather
    than registering a function so that FastMCP's TypeAdapter cannot refuse or coerce a
    payload before our accepted shape decides. Two validators for one policy is the defect;
    this makes REST agree with the other two.

    The published contract does not change: the route advertises ``dto.model_json_schema()``
    through ``openapi_extra``, derived from the same model that validates.

    PATH FIELDS are the one place the body is not the whole request. A row whose path is
    templated (``PUT /media-buys/{media_buy_id}``) names those fields in ``path_fields``, and
    the URL is the resource identity, so the path value WINS over a body that disagrees. With
    a raw body that merge is a dict update, and the relaxed DTO subclass that existed only to
    survive FastAPI's pre-validation is gone with it.
    """

    async def handler(request: Request, auth_ctx: AuthContext = get_auth_context, **path_values: Any) -> Any:
        body = await request.json()
        # ONE try around everything that can produce a failure response, so every failure
        # leaves through the same except and none can escape as a 500.
        try:
            if path_values:
                # The URL is the resource identity, so a path value WINS over a body that
                # disagrees, and the merge happens before validation because the DTO requires
                # the field. A body that is not a JSON object cannot take a path value and is
                # not an AdCP request: answered as malformed, not as a 500 from the merge.
                # Caught, not probed for type -- the same shape as the raw context read.
                try:
                    body = {**body, **path_values}
                except TypeError:
                    # Not a JSON object, so it cannot take a path value. Handed on UNMERGED
                    # rather than rejected here: ``validated_request`` refuses it with the same
                    # INVALID_REQUEST and ``issues`` every other row's malformed body earns,
                    # where a rejection minted here answered it without the issues -- one
                    # payload, two shapes, depending on whether the route was templated.
                    pass
            # Named, not frozen: the handler names the TOOL and ``serve`` reads the registry
            # per call. A route that froze the callable at import could not be substituted --
            # the registry row and the thing the route invoked were two different objects.
            #
            # It hands over the CREDENTIAL, not an identity. Resolving it here meant reading
            # ToolSpec.auth here too -- via two dependencies picked by `spec.auth == "optional"`,
            # one of which hardcoded require_valid_token=False and made REST the only transport
            # that served a rejected credential on a public tool.
            response = await serve(tool_name, body, auth_ctx, TransportProtocol.REST)
        except AdcpFailure as failure:
            # REST's wire failure marker is the HTTP STATUS, and that is all this transport
            # adds. The BODY is the response the boundary built, serialized by the same
            # function the success path uses.
            return JSONResponse(status_code=wire_status(failure.response), content=to_wire(failure.response))
        return JSONResponse(status_code=200, content=to_wire(response))

    handler.__name__ = tool_name
    handler.__doc__ = (spec.impl.__doc__ or "").strip().split("\n")[0]
    path_params = [
        # Typed from the DTO field, so the path segment is validated as the field it fills.
        inspect.Parameter(
            name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=spec.dto.model_fields[name].annotation,
        )
        for name in sorted(spec.rest.path_fields)
    ]
    apply_signature(
        handler,
        inspect.Signature(
            [
                *path_params,
                # ``Request``, not the DTO: a typed body parameter is exactly what makes
                # FastAPI validate before the handler runs.
                inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
                # ONE parameter for every row. It used to be an ``identity`` whose
                # dependency and annotation both keyed off ``spec.auth``; the boundary
                # decides now, so the route carries the same credential either way.
                inspect.Parameter(
                    "auth_ctx",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=get_auth_context,
                    annotation=AuthContext,
                ),
            ]
        ),
    )
    return handler


def _rest_body_schemas() -> tuple[dict[type[Any], dict[str, Any]], dict[str, Any]]:
    """Every REST DTO's request-body schema, and the ONE ``$defs`` they all refer into.

    One ``models_json_schema`` call over all the DTOs, so pydantic assigns each nested model
    a name that is unique ACROSS the set. Generating per-DTO and merging by name let two models
    that happened to share a name -- ``Status``, ``Disclosure``, seventeen of them -- overwrite
    each other in ``components/schemas``, so a ref from one tool resolved to another tool's
    definition.
    """
    from pydantic import BaseModel
    from pydantic.json_schema import models_json_schema

    # ``cast`` states a guarantee the registry already enforces: ``_register_tool`` refuses a
    # row whose DTO is not a pydantic model, but a row's static type is the ``BuyerRequest``
    # mixin, which cannot say so.
    dtos: list[type[BaseModel]] = [cast(type[BaseModel], spec.dto) for spec in TOOLS.values() if spec.rest is not None]
    per_model, shared = models_json_schema(
        [(dto, "validation") for dto in dtos], ref_template="#/components/schemas/{model}"
    )
    return {dto: per_model[(dto, "validation")] for dto in dtos}, shared.get("$defs", {})


_BODY_SCHEMA_BY_DTO, REST_COMPONENT_SCHEMAS = _rest_body_schemas()


for _name, _spec in TOOLS.items():
    if _spec.rest is None:
        continue
    # The DTO is ADVERTISED here, not enforced: ``openapi_extra`` publishes the model's own
    # JSON Schema so a client reads the shape it always did, while the handler receives the
    # payload untouched and ``serve`` decides it. Both come from one declaration, so the
    # advertised shape and the accepted shape cannot drift.
    #
    # ``$ref``s point into ``#/components/schemas``, and the nested models they name are
    # published there by ``src.app``'s OpenAPI hook. A verbatim ``model_json_schema()`` puts
    # its ``$defs`` at the root of the SCHEMA, but a schema nested under a request body is not
    # the root of the DOCUMENT, so its ``#/$defs/...`` pointers resolved against the document
    # and found nothing -- 1466 dangling references under a comment claiming the contract was
    # unchanged.
    router.add_api_route(
        _spec.rest.path,
        _rest_handler(_name, _spec),
        methods=[_spec.rest.verb],
        name=_name,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _BODY_SCHEMA_BY_DTO[_spec.dto]}},
            }
        },
    )
