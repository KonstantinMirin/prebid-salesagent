# MCP & A2A Patterns

Reference patterns for working with MCP tools and A2A integration. Read this when adding or modifying tools.

## MCP Client Usage
```python
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

headers = {"Authorization": "Bearer your_token"}
transport = StreamableHttpTransport(url="http://localhost:8000/mcp/", headers=headers)
client = Client(transport=transport)

async with client:
    products = await client.tools.get_products(brief="video ads")
    result = await client.tools.create_media_buy(product_ids=["prod_1"], ...)
```

## CLI Testing
```bash
# List available tools
uvx adcp http://localhost:8000/mcp/ --auth test-token list_tools

# A real token is shown once, when the advertiser is created (or rotated) in Admin UI -> Advertisers
uvx adcp http://localhost:8000/mcp/ --auth <real-token> get_products '{"brief":"video"}'
```

## Transport Boundary: One Path to Every Implementation (Critical Pattern #5)

A transport parses a request and writes a response. Between it and the business logic sits
ONE seam, `src/core/tools/_boundary.py`. There are no per-tool wrappers.

**`_impl` functions** (transport-agnostic):
```python
async def _create_media_buy_impl(
    req: CreateMediaBuyRequest,
    identity: ResolvedIdentity,    # never Context, headers or a token
) -> CreateMediaBuyResult:
    ...
```

**Every transport** names the tool and hands over the raw payload and the request headers:
```python
response = await serve("create_media_buy", payload, headers, TransportProtocol.A2A)
```

`serve` validates the payload into the registry row's DTO, resolves the identity once
(the resolver is private to the boundary), resolves the account the request names, honours
its `idempotency_key`, and stamps the buyer's `context` onto the response — once, for every
transport.

**`_impl` rules:** Accept `ResolvedIdentity` (not Context). Raise `AdCPSalesAgentError` (not
ToolError). Zero imports from fastmcp/a2a/starlette/fastapi. No account resolution, no
idempotency, no context echo. Declare exactly `(req: <DTO>, identity: ResolvedIdentity)`.

**Transport rules:** Hand over the headers, call `serve`, catch `AdcpFailure`, serialize
its response with `to_wire`, add only the transport's own failure marker.

**Substituting an implementation in a test** patches the registry ROW — `TOOLS` holds the
function object, so patching a module attribute renames something nothing consults. Use
`stub_impl` / `registry_impl` from `tests/helpers/capture_wrapper_req.py`.

**Enforced by 4 structural guards** — see `docs/development/structural-guards.md`.

## Access Points (via nginx at http://localhost:8000)
- Admin UI: `/admin/` or `/tenant/default`
- MCP Server: `/mcp/`
- A2A Server: `/a2a`
