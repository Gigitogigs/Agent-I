# API Reference

The backend exposes a REST API via FastAPI under `/api/v1`. 
*Note: While architectural plans mention WebSockets, the current codebase relies entirely on HTTP endpoints.*

## Authentication (`/api/v1/auth`)
- `POST /login`: Accepts OAuth2 credentials, returns a JWT `access_token` and a refresh token.
- **Usage**: Most endpoints require the `Authorization: Bearer <token>` header.

## Chat (`/api/v1/chat`)
- `POST /`: Submit a message to the orchestrator.
  - **Request**: `{ "message": "string", "conversation_id": "uuid" (optional) }`
  - **Behavior**: This invokes the `root_agent` LangGraph synchronously. If a guardrail interrupts the flow for HITL approval, this returns an HTTP 200 with a status indicating the conversation is paused pending approval.

## Approvals (`/api/v1/approvals`)
- `GET /`: List pending High-Risk action approvals for the current workspace.
- `POST /{approval_id}/approve`: Submits an operator's decision.
  - **Behavior**: Updates the `approval_requests` table and enqueues an ARQ task (`resume_agent_graph`) which unpauses the LangGraph using `Command(resume=decision)`.

## Workspaces & Members (`/api/v1/workspaces`, `/api/v1/members`)
- Workspace and multi-tenancy management. The `WorkspaceContextMiddleware` automatically injects `workspace_id` into the request state for these operations based on the active JWT.

## Knowledge Base (`/api/v1/knowledge`)
- `POST /upload`: Uploads a document to the knowledge base.
- **Behavior**: Triggers the `process_document_task` in the ARQ worker to chunk the text and insert embeddings into pgvector.

## Agents & Providers (`/api/v1/agents`, `/api/v1/providers`)
- CRUD endpoints for managing LLM configurations and provider API keys (which are encrypted at rest using the `ENCRYPTION_KEY`).

*Last verified against commit/code state: Checked backend/api/routers directory, backend/main.py, and support_system/subagents/escalation_agent/graph.py.*
