from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.api.routers import health
from backend.api.routers import auth
from backend.api.routers import workspaces
from backend.api.routers import account
from backend.api.routers import members
from backend.api.routers import approvals
from backend.api.routers import chat
from backend.middleware import WorkspaceContextMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# ---------------------------------------------------------------------------
# Middleware (order matters — outermost is added first)
# ---------------------------------------------------------------------------

# CORS — must come before WorkspaceContextMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # TODO: Replace with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inject user_id / workspace_id into request.state from the Bearer token
app.add_middleware(WorkspaceContextMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router, prefix=settings.API_V1_STR, tags=["health"])
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["auth"])
app.include_router(workspaces.router, prefix=settings.API_V1_STR, tags=["workspaces"])
app.include_router(account.router, prefix=settings.API_V1_STR, tags=["account"])
app.include_router(members.router, prefix=settings.API_V1_STR, tags=["members"])
app.include_router(approvals.router, prefix=settings.API_V1_STR, tags=["approvals"])
app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["chat"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
