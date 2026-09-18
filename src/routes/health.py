"""Health and debug endpoints.

Extracted from src/core/main.py @mcp.custom_route handlers into
standard FastAPI routes so they are served by the unified FastAPI app.
"""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from src.core.config_loader import get_tenant_by_virtual_host
from src.core.database.database_session import get_db_session
from src.core.database.models import Product as ModelProduct
from src.core.database.models import Tenant as ModelTenant
from src.core.database.repositories.principal import PrincipalRepository
from src.landing import generate_tenant_landing_page

logger = logging.getLogger(__name__)

router = APIRouter()


# The routes on this router exist only where the deployment allows them: ``src/app.py``
# includes it when ``get_settings().debug_routes_enabled`` says so, and nowhere else does it
# exist at all. No per-request check: a route that is not mounted cannot be reached.
debug_router = APIRouter()


@router.get("/health")
async def health(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "mcp"})


@debug_router.post("/_internal/reset-db-pool")
async def reset_db_pool(request: Request):
    """Reset database connection pool after external data changes.

    A testing-only endpoint that flushes the SQLAlchemy connection pool, so fresh
    connections see recently committed data. On the debug router, so it exists only where
    the deployment mounts that router.
    """
    try:
        from src.core.database.database_session import reset_engine

        logger.info("Resetting database connection pool and tenant context (testing mode)")

        reset_engine()
        logger.info("  ✓ Database connection pool reset")

        return JSONResponse(
            {
                "status": "success",
                "message": "Database connection pool and tenant context reset successfully",
            }
        )
    except Exception as e:
        logger.error(f"Failed to reset database state: {e}")
        return JSONResponse({"error": f"Failed to reset: {str(e)}"}, status_code=500)


@debug_router.get("/debug/db-state")
async def debug_db_state(request: Request):
    """Debug endpoint to show database state (testing only)."""
    try:
        with get_db_session() as session:
            product_stmt = select(ModelProduct)
            all_products = session.scalars(product_stmt).all()

            # The CI seed, by its stable slug, then the principal inside it. No token is
            # turned into a principal here; the seed tenant holds exactly one principal,
            # and this route only reports whether the seed exists.
            #
            # A direct read of a KNOWN row's id -- this is a debug report about the CI seed,
            # not a request identifying its seller. The id is the seed's stable spelling
            # (scripts/setup/init_database_ci.py CI_TEST_TENANT_ID); src/ does not import
            # from scripts/, so the literal is repeated rather than shared.
            seed_tenant_id = session.scalars(
                select(ModelTenant.tenant_id).filter_by(tenant_id="ci-test", is_active=True)
            ).first()
            principal = (
                next(iter(PrincipalRepository(session, seed_tenant_id).list_all()), None) if seed_tenant_id else None
            )

            principal_info = None
            tenant_info = None
            tenant_products: list[ModelProduct] = []

            if principal:
                principal_info = {
                    "principal_id": principal.principal_id,
                    "tenant_id": principal.tenant_id,
                }

                tenant_stmt = select(ModelTenant).filter_by(tenant_id=principal.tenant_id)
                tenant = session.scalars(tenant_stmt).first()
                if tenant:
                    tenant_info = {
                        "tenant_id": tenant.tenant_id,
                        "name": tenant.name,
                        "is_active": tenant.is_active,
                    }

                tenant_product_stmt = select(ModelProduct).filter_by(tenant_id=principal.tenant_id)
                tenant_products = list(session.scalars(tenant_product_stmt).all())

            return JSONResponse(
                {
                    "total_products": len(all_products),
                    "principal": principal_info,
                    "tenant": tenant_info,
                    "tenant_products_count": len(tenant_products),
                    "tenant_product_ids": [p.product_id for p in tenant_products],
                }
            )
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@debug_router.get("/debug/tenant")
async def debug_tenant(request: Request):
    """Debug endpoint to check tenant detection from headers."""
    headers = dict(request.headers)

    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")

    tenant_id = None
    tenant_name = None
    detection_method = None

    if apx_host:
        tenant_row = get_tenant_by_virtual_host(apx_host)
        if tenant_row:
            tenant_id = tenant_row.get("tenant_id")
            tenant_name = tenant_row.get("name")
            detection_method = "apx-incoming-host"

    if not tenant_id and host_header:
        # The Host, against virtual_host — the same lookup the resolver does. It used to
        # report a "host-subdomain" method that guessed the tenant_id from the first label
        # without consulting any row; that strategy is gone, and a
        # debug endpoint claiming a detection method production does not have is worse than
        # no endpoint.
        tenant_row = get_tenant_by_virtual_host(host_header)
        if tenant_row:
            tenant_id = tenant_row.get("tenant_id")
            tenant_name = tenant_row.get("name")
            detection_method = "host"

    response_data = {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "detection_method": detection_method,
        "apx_incoming_host": apx_host,
        "host": host_header,
    }

    response = JSONResponse(response_data)
    if tenant_id:
        response.headers["X-Tenant-Id"] = tenant_id

    return response


@debug_router.get("/debug/root")
async def debug_root(request: Request):
    """Debug endpoint to test root route logic without redirects."""
    headers = dict(request.headers)

    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")

    virtual_host = apx_host or host_header

    tenant_row = get_tenant_by_virtual_host(virtual_host) if virtual_host else None

    debug_info = {
        "all_headers": headers,
        "apx_host": apx_host,
        "host_header": host_header,
        "virtual_host": virtual_host,
        "tenant_found": tenant_row is not None,
        "tenant_id": tenant_row.get("tenant_id") if tenant_row else None,
        "tenant_name": tenant_row.get("name") if tenant_row else None,
    }

    if tenant_row:
        try:
            html_content = generate_tenant_landing_page(tenant_row, virtual_host)
            debug_info["landing_page_generated"] = True
            debug_info["landing_page_length"] = len(html_content)
        except Exception as e:
            debug_info["landing_page_generated"] = False
            debug_info["landing_page_error"] = str(e)

    return JSONResponse(debug_info)


@debug_router.get("/debug/landing")
async def debug_landing(request: Request):
    """Debug endpoint to test landing page generation directly."""
    headers = dict(request.headers)

    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")
    virtual_host = apx_host or host_header

    if virtual_host:
        tenant_row = get_tenant_by_virtual_host(virtual_host)
        if tenant_row:
            try:
                html_content = generate_tenant_landing_page(tenant_row, virtual_host)
                return HTMLResponse(content=html_content)
            except Exception as e:
                return JSONResponse({"error": f"Landing page generation failed: {e}"}, status_code=500)

    return JSONResponse({"error": "No tenant found"}, status_code=404)


@debug_router.get("/debug/root-logic")
async def debug_root_logic(request: Request):
    """Debug endpoint that exactly mimics the root route logic for testing."""
    headers = dict(request.headers)

    apx_host = headers.get("apx-incoming-host") or headers.get("Apx-Incoming-Host")
    host_header = headers.get("host") or headers.get("Host")
    virtual_host = apx_host or host_header

    debug_info: dict[str, Any] = {
        "step": "initial",
        "virtual_host": virtual_host,
        "apx_host": apx_host,
        "host_header": host_header,
    }

    if virtual_host:
        debug_info["step"] = "virtual_host_found"

        tenant_row = get_tenant_by_virtual_host(virtual_host)
        debug_info["exact_tenant_lookup"] = tenant_row is not None

        # No subdomain fallback to report: tenant detection has one host lookup
        # , so an exact virtual_host miss IS the answer.

        if tenant_row:
            debug_info["step"] = "tenant_found"
            debug_info["tenant_id"] = tenant_row.get("tenant_id")
            debug_info["tenant_name"] = tenant_row.get("name")

            try:
                html_content = generate_tenant_landing_page(tenant_row, virtual_host)
                debug_info["step"] = "landing_page_success"
                debug_info["landing_page_length"] = len(html_content)
                debug_info["would_return"] = "HTMLResponse"
            except Exception as e:
                debug_info["step"] = "landing_page_error"
                debug_info["error"] = str(e)
                debug_info["would_return"] = "fallback HTMLResponse"
        else:
            debug_info["step"] = "no_tenant_found"
            debug_info["would_return"] = "redirect to /admin/"
    else:
        debug_info["step"] = "no_virtual_host"
        debug_info["would_return"] = "redirect to /admin/"

    return JSONResponse(debug_info)


@router.get("/health/config")
async def health_config(request: Request):
    """Configuration health check endpoint."""
    try:
        from src.core.startup import validate_startup_requirements

        validate_startup_requirements()
        return JSONResponse(
            {
                "status": "healthy",
                "service": "mcp",
                "component": "configuration",
                "message": "All configuration validation passed",
            }
        )
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "service": "mcp", "component": "configuration", "error": str(e)}, status_code=500
        )
