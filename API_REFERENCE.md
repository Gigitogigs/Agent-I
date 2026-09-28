# API Reference

The backend exposes a REST API and a WebSocket interface via FastAPI under `/api/v1`.

> **Interactive docs**: `http://localhost:8000/api/v1/docs` (Swagger UI) and `/api/v1/redoc` (ReDoc) are available when the server is running.

---

## Authentication — `/api/v1/auth`

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Create a new user account |
| `POST` | `/auth/login` | Public | Returns JWT `access_token` + `refresh_token` |
| `POST` | `/auth/refresh` | Public | Exchange a refresh token for a new access token |
| `POST` | `/auth/logout` | Authenticated | Revokes the current session |
| `POST` | `/auth/forgot-password` | Public | Sends a password reset email |
| `POST` | `/auth/reset-password` | Public | Completes a password reset using a token |

Most other endpoints require `Authorization: Bearer <access_token>`.

---

## Health — `/api/v1/health`

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{ "status": "ok" }` |

---

## Workspaces — `/api/v1/workspaces`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `POST` | `/workspaces` | Authenticated | Create a new workspace |
| `GET` | `/workspaces` | Authenticated | List workspaces the current user belongs to |
| `DELETE` | `/workspaces/{id}` | `owner` | Soft-delete (schedules hard-delete after 48h grace period) |
| `POST` | `/workspaces/{id}/cancel-deletion` | `owner` | Cancel a pending soft-delete |

---

## Members — `/api/v1/workspaces/{workspace_id}/members`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/members` | `admin` | List all workspace members |
| `POST` | `/members/invite` | `admin` | Invite a user by email |
| `PUT` | `/members/{user_id}/role` | `admin` | Update a member's role |
| `DELETE` | `/members/{user_id}` | `admin` | Remove a member |

---

## Chat (HTTP) — `/api/v1/workspaces/{workspace_id}/conversations`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `POST` | `/{conversation_id}/chat` | `read-only` | Submit a message; invokes the agent graph synchronously |
| `GET` | `` | `read-only` | List conversations (supports `status`, `search`, cursor pagination) |
| `GET` | `/{conversation_id}` | `read-only` | Get conversation details and full transcript |

**Idempotency**: The `POST .../chat` endpoint accepts an optional `Idempotency-Key` request header.
- If a key is provided and the request is in-flight: `409 Conflict`
- If a key is provided and the request succeeded previously: returns the cached response (no LLM invocation)
- If the request fails: the lock is released so the client can safely retry

---

## Chat (WebSocket) — `/api/v1/workspaces/{workspace_id}/conversations`

| Protocol | Path | Description |
|---|---|---|
| `WS` | `/{conversation_id}/ws` | Real-time streaming chat via WebSocket |

**Authentication**: Pass the JWT in the `Sec-WebSocket-Protocol` header as `access_token.<token>`.

**Client → Server messages:**
```json
{ "type": "ping" }
{ "type": "message", "content": "User's message here" }
```

**Server → Client frames:**
```json
{ "type": "pong" }
{ "type": "agent_status", "status": "thinking" }
{ "type": "token", "content": "..." }
{ "type": "turn_complete", "turn_id": "uuid", "subagent_results": {} }
{ "type": "error", "detail": "..." }
```

> **Limitation**: Only one WebSocket connection is supported per `conversation_id`. A second connection silently replaces the first.

---

## Approvals — `/api/v1/workspaces/{workspace_id}/approvals`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `` | `operator` | List approval requests (filter by `status`) |
| `POST` | `/{app_id}/approve` | `operator` | Approve a pending action; enqueues ARQ task to resume graph |
| `POST` | `/{app_id}/reject` | `operator` | Reject a pending action with an optional `reason` |

Both `approve` and `reject` accept an `Idempotency-Key` header using the same Redis locking/caching mechanism as the chat endpoint.

**Illegal transitions** return `409 Conflict` (e.g. approving an already-approved request).

---

## Knowledge Base — `/api/v1/workspaces/{workspace_id}/knowledge`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `POST` | `/upload` | `admin` | Upload a document (PDF, DOCX, XLSX, CSV, TXT). Triggers ARQ `process_document_task` to chunk and embed into pgvector. |
| `GET` | `` | `read-only` | List documents and their processing status |
| `DELETE` | `/{document_id}` | `admin` | Delete a document and all its chunks/embeddings |

---

## Agents & Config — `/api/v1/workspaces/{workspace_id}/agents`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/config` | `admin` | Get the workspace's active LLM configuration |
| `PUT` | `/config` | `admin` | Update model, temperature, system prompt, HITL breakpoints |

---

## Providers — `/api/v1/workspaces/{workspace_id}/providers`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `` | `admin` | List available providers and whether an API key is configured |
| `PUT` | `/{provider}/key` | `admin` | Store or update an encrypted API key for a provider |
| `DELETE` | `/{provider}/key` | `admin` | Remove a stored API key |
| `POST` | `/{provider}/verify` | `admin` | Test connectivity with the stored key |

---

## Settings — `/api/v1/workspaces/{workspace_id}/settings`

### Notification Channels
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/notifications` | `admin` | List notification channels |
| `POST` | `/notifications` | `admin` | Create a new channel (e.g. Slack webhook) |
| `PUT` | `/notifications/{channel_id}` | `admin` | Update a channel |

### Billing
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/billing` | `owner` | Get billing details for the workspace |

### Integrations
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/integrations` | `admin` | List external integrations (e.g. Shopify) |
| `POST` | `/integrations` | `admin` | Add a new integration |
| `DELETE` | `/integrations/{id}` | `admin` | Remove an integration |
| `POST` | `/integrations/{id}/verify` | `admin` | Verify connectivity for an integration |

---

## Account — `/api/v1/account`

| Method | Path | Description |
|---|---|---|
| `GET` | `/account/me` | Get the current user's profile |
| `PUT` | `/account/me` | Update name / password |

---

*Last verified against: `backend/main.py`, `backend/api/routers/*.py` — 2026-09-28*
