"""
backend/middleware/workspace_ctx.py

Lightweight ASGI middleware that parses the Bearer access token on every
request (without re-querying the DB) and injects workspace context into
request.state. This makes workspace_id available to any downstream code
(logging, tracing, rate-limiting) without a Depends() call.

Note: This middleware does NOT enforce authentication — it only enriches
request.state if a valid token is present. Auth enforcement happens at the
route level via Depends(get_current_user).
"""
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.core.security import decode_token


class WorkspaceContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.user_id = None
        request.state.workspace_id = None

        auth_header: Optional[str] = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[len("Bearer "):]
            try:
                payload = decode_token(raw_token)
                if payload.get("type") == "access":
                    request.state.user_id = payload.get("sub")
                    # workspace_id is written here if the client sends it in a
                    # header (X-Workspace-Id). Workspace-scoped routes also
                    # resolve this via the path parameter in get_current_membership.
                    workspace_id_header = request.headers.get("X-Workspace-Id")
                    if workspace_id_header:
                        request.state.workspace_id = workspace_id_header
            except Exception:
                # Silently swallow — auth enforcement is handled at the route level
                pass

        return await call_next(request)
