"""Shared API key authentication helpers for admin blueprints.

Provides a parameterized auth decorator factory used by both
tenant_management_api and sync_api to avoid duplicating the
header-read → key-lookup → hmac-compare flow.
"""

from __future__ import annotations

import hmac
import logging
from functools import wraps
from typing import Any

from flask import jsonify, request
from sqlalchemy import select

from src.core.config import get_settings
from src.core.database.database_session import get_db_session
from src.core.database.models import TenantManagementConfig

logger = logging.getLogger(__name__)


def get_api_key_from_config(configured: str | None, config_key: str) -> str | None:
    """Get API key from the configured value (priority) or DB TenantManagementConfig.

    Args:
        configured: The key as the settings carry it (``None`` when unset)
        config_key: TenantManagementConfig.config_key to fall back to
    """
    if configured:
        return configured

    with get_db_session() as session:
        stmt = select(TenantManagementConfig).filter_by(config_key=config_key)
        config = session.scalars(stmt).first()
        if config and config.config_value:
            return config.config_value
    return None


def require_api_key_auth(*, setting: str, config_key: str, header: str) -> Any:
    """Factory that returns a Flask decorator for API key authentication.

    Args:
        setting: The ``AuthSettings`` field carrying the key. It is read per request,
            so a settings reload is seen without rebuilding the decorator. The field
            name upper-cased is the variable an operator sets, which is what the
            503 body names.
        config_key: TenantManagementConfig.config_key for DB fallback
        header: HTTP header name to read the key from
    """
    env_var = setting.upper()

    def decorator(f: Any) -> Any:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            api_key = request.headers.get(header)

            if not api_key:
                return jsonify({"error": "Missing API key"}), 401

            configured: str | None = getattr(get_settings().auth, setting)
            valid_key = get_api_key_from_config(configured, config_key)
            if not valid_key:
                logger.error(f"API key not configured (setting: {env_var}, db: {config_key})")
                return jsonify({"error": f"API not configured. Set {env_var} environment variable."}), 503

            if not hmac.compare_digest(api_key, valid_key):
                logger.warning(f"Invalid API key attempted (header: {header})")
                return jsonify({"error": "Invalid API key"}), 401

            return f(*args, **kwargs)

        return decorated_function

    return decorator
