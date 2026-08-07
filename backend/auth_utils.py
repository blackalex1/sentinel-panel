"""
Facade module re-exporting symbols from backend.auth package for backward compatibility.
"""
from backend.database import get_setting
from backend.auth import (
    is_safe_url,
    DbCsrfTokens,
    DbActiveSessions,
    ACTIVE_SESSIONS,
    CSRF_TOKENS,
    check_auth,
    verify_node_token,
    verify_telegram_webapp,
    DecoyException,
    RawDropResponse,
    decoy_response_html,
    decoy_response,
    render_static_decoy,
    proxy_decoy_request,
    handle_decoy_route,
)

__all__ = [
    "get_setting",
    "is_safe_url",
    "DbCsrfTokens",
    "DbActiveSessions",
    "ACTIVE_SESSIONS",
    "CSRF_TOKENS",
    "check_auth",
    "verify_node_token",
    "verify_telegram_webapp",
    "DecoyException",
    "RawDropResponse",
    "decoy_response_html",
    "decoy_response",
    "render_static_decoy",
    "proxy_decoy_request",
    "handle_decoy_route",
]
