# Frontend Interaction Contract

> The admin frontend lives in a separate repository. This document defines the HTTP and WebSocket contract that the frontend must conform to. Last verified 2026-09-28.

---

## Base URL

```
http://localhost:8000/api/v1
```

CORS is configured to allow `http://localhost:3000` and `http://127.0.0.1:3000`. Update `backend/main.py` (`allow_origins`) when deploying to production.

---

## Authentication

All requests (except `/auth/login`, `/auth/register`, `/auth/refresh`) require:
```
Authorization: Bearer <access_token>
```

Tokens are short-lived JWTs. Use `POST /auth/refresh` with the `refresh_token` to obtain a new access token.

---

## Chat — Two Modes

### Option A: HTTP (Simple)
```
POST /workspaces/{workspace_id}/conversations/{conversation_id}/chat
Content-Type: application/json
Idempotency-Key: <unique-string>   (optional but recommended)

{ "message": "Hello" }
```
Returns the full agent response in a single HTTP response. Recommended for simple integrations or fallback.

### Option B: WebSocket (Streaming)
```
WS /workspaces/{workspace_id}/conversations/{conversation_id}/ws
Sec-WebSocket-Protocol: access_token.<jwt>
```

**Expected event flow for a single turn:**
1. Client sends `{ "type": "message", "content": "..." }`
2. Server sends `{ "type": "agent_status", "status": "thinking" }`
3. Server streams N frames: `{ "type": "token", "content": "<partial text>" }`
4. Server sends `{ "type": "turn_complete", "turn_id": "...", "subagent_results": {} }`

Use the `turn_id` from `turn_complete` to associate the completed turn with a DB record.

> Only one WebSocket per `conversation_id` is supported. Implement reconnection logic on disconnect.

---

## Idempotency Keys

For both chat (`POST .../chat`) and approval actions, it is recommended to send a client-generated `Idempotency-Key` header (a UUID or similar unique string per user action). This prevents:
- **Double-submits** from button spam → `409 Conflict` with `"Request in progress"`
- **Network retries** from returning duplicate agent responses → cached `200 OK`

---

## Approval Flow

When a HITL event occurs, the agent response will indicate a paused state. The frontend should:
1. Poll or listen for new entries via `GET /workspaces/{id}/approvals?status=PENDING`
2. Display approval details to the operator
3. Call `POST /workspaces/{id}/approvals/{app_id}/approve` or `.../reject`
4. The backend ARQ worker resumes the graph; the conversation's next message will arrive via WebSocket or the next HTTP poll

---

## Pagination

`GET /workspaces/{id}/conversations` supports cursor-based pagination:
- Pass `cursor=<value>` returned in `nextCursor` from the previous response
- `limit` defaults to 50

---

## Error Conventions

| Status | Meaning |
|---|---|
| `400` | Bad request (validation error) |
| `401` | Missing or invalid JWT |
| `403` | Insufficient role |
| `404` | Resource not found (also used instead of 403 in some IDOR-sensitive paths) |
| `409` | Conflict (idempotency lock, illegal state transition) |
| `500` | Unexpected server/agent error |

WebSocket close codes:
- `4001` — Unauthorized
- `4003` — Conversation is closed/resolved
- `4004` — Conversation not found


## Connector Catalog Updates
Added /connector-catalog endpoint for dynamic connector discovery. WorkspaceIntegration now includes domain and is_primary to isolate active connectors per domain.
