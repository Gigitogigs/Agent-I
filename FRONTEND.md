# Frontend Integration

The Next.js admin frontend lives in a **separate repository**. This document describes how the frontend integrates with the Agent-I backend.

## Cross-Origin Resource Sharing (CORS)
The backend expects the frontend to operate at the origin defined by the `FRONTEND_URL` environment variable (default: `http://localhost:3000`).
The backend's `CORSMiddleware` (`backend/main.py`) explicitly whitelists `http://localhost:3000` and `http://127.0.0.1:3000`. If you deploy the frontend elsewhere, you must update the backend configuration to allow the new origin.

## Authentication Flow
- **Login**: Frontend sends credentials to `/api/v1/auth/login`. Returns a standard OAuth2 `access_token` (JWT) and a refresh token.
- **Headers**: All protected endpoints require an `Authorization: Bearer <token>` header.
- **Context Injection**: The `WorkspaceContextMiddleware` intercepts the token and automatically injects the `user_id` and `workspace_id` into the request state.

## Core Interaction Points
1. **Chat**: 
   - No WebSockets are used.
   - The frontend communicates via standard HTTP POSTs to `/api/v1/chat/...`
   - When an action triggers a Human-in-the-Loop (HITL) interrupt, the backend will return a state indicating the conversation is paused pending approval.
2. **Approvals**:
   - The frontend polls or loads the pending approvals from `/api/v1/approvals`.
   - When an operator approves/rejects, a POST is sent to the approval endpoint, which enqueues a background task (`resume_agent_graph`) to unpause the LangGraph execution.

## Known Gaps
- Since there are no WebSockets, the frontend must currently rely on HTTP polling or manual refreshing to detect when a background ARQ task (like document processing or graph resumption) completes.

*Last verified against commit/code state: Checked backend/main.py (CORS) and missing frontend directory.*
