# Agent-I API Contract

This document outlines the REST API specification required by the Agent-I frontend. It is the source of truth for backend engineers implementing compatible endpoints.

**Base URL:** All endpoints are prefixed with `/api/v1/`
**Auth:** JWT delivered via HTTP-only cookies (`access_token` + `refresh_token`). The backend validates the access token on every authenticated request. On expiry, the client calls `POST /auth/refresh` silently.
**Content-Type:** `application/json` unless noted as `multipart/form-data`.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Workspaces & Account Deletion](#2-workspaces--account-deletion)
3. [Team & Roles](#3-team--roles)
4. [Approvals (HITL Queue)](#4-approvals-hitl-queue)
5. [Conversations](#5-conversations)
6. [Knowledge Base](#6-knowledge-base)
7. [Agent Configuration](#7-agent-configuration)
8. [Agent Stats](#8-agent-stats)
9. [Settings — Profile](#9-settings--profile)
10. [Settings — Notifications](#10-settings--notifications)
11. [Settings — Billing](#11-settings--billing)
12. [Settings — Integrations](#12-settings--integrations)
13. [Homepage Summary](#13-homepage-summary)
14. [Providers & API Keys](#14-providers--api-keys)
15. [Standard Error Responses](#15-standard-error-responses)

---

## 1. Authentication

### `POST /auth/login`
- **Auth required:** No
- **Request:** `{"email": "...", "password": "..."}`
- **Response:** `200 OK`
  ```json
  {
    "user": {
      "id": "usr_123",
      "name": "Jane Doe",
      "email": "jane@example.com",
      "avatarUrl": "https://..."
    },
    "activeWorkspaceId": "ws_123",
    "workspaceDeletionStatus": null
  }
  ```
  > `workspaceDeletionStatus` is `"grace_period"` if the active workspace is scheduled for deletion within 48hr, `"account_grace_period"` if the user's account is scheduled for deletion, otherwise `null`. The frontend renders a takeover screen if non-null.
  > Sets HTTP-only cookies: `access_token` (15 min) and `refresh_token` (7 days).

### `POST /auth/signup`
- **Auth required:** No
- **Request:** `{"name": "...", "email": "...", "password": "..."}`
- **Response:** `201 Created` (same shape as login response — user is immediately logged in)

### `POST /auth/logout`
- **Auth required:** Yes
- **Request:** empty body
- **Response:** `200 OK` (clears cookies, invalidates refresh token)

### `POST /auth/refresh`
- **Auth required:** No (uses `refresh_token` cookie)
- **Response:** `200 OK` (issues new `access_token` cookie)

### `POST /auth/forgot-password`
- **Auth required:** No
- **Request:** `{"email": "..."}`
- **Response:** `200 OK` (always, to prevent email enumeration)

### `POST /auth/reset-password`
- **Auth required:** No
- **Request:** `{"token": "...", "newPassword": "..."}`
- **Response:** `200 OK`

---

## 2. Workspaces & Account Deletion

### `GET /workspaces`
- **Auth required:** Yes
- **Response:** Array of all workspaces the current user is a member of.
  ```json
  [
    {
      "id": "ws_123",
      "name": "Acme Corp",
      "role": "owner",
      "deletionScheduledAt": null
    }
  ]
  ```

### `POST /workspaces`
- **Auth required:** Yes
- **Request:** `{"name": "..."}`
- **Response:** `201 Created` — returns the new workspace object (same shape as above).

### `DELETE /workspaces/{id}`
- **Auth required:** Yes (Owner role only)
- **Request:** `{"password": "..."}` — password is re-validated server-side.
- **Response:** `202 Accepted`
- **Behavior:** Sets `workspaces.deletion_scheduled_at = NOW()`. Does not delete immediately. Enqueues a confirmation email.

### `POST /workspaces/{id}/cancel-deletion`
- **Auth required:** Yes (Owner only)
- **Response:** `200 OK` — clears `deletion_scheduled_at`, workspace is restored immediately.

### `DELETE /account`
- **Auth required:** Yes (Owner only — per system rules, only owners initiate account deletion)
- **Request:** `{"password": "..."}` — password is re-validated server-side.
- **Response:** `202 Accepted`
- **Behavior:**
  1. Sets `users.deletion_scheduled_at = NOW()`.
  2. Sets `workspaces.deletion_scheduled_at = NOW()` for every workspace this user owns.
  3. Immediately invalidates all active sessions (unlike workspace deletion, account deletion logs you out).
  4. Enqueues a confirmation email.

### `POST /account/cancel-deletion`
- **Auth required:** Yes
- **Response:** `200 OK` — clears `users.deletion_scheduled_at` AND `workspaces.deletion_scheduled_at` for all owned workspaces.

---

## 3. Team & Roles

> All endpoints are scoped to the active workspace.
> Roles: `owner`, `admin`, `operator`, `read_only`

### `GET /workspaces/{id}/members`
- **Auth required:** Yes (Admin+)
- **Response:**
  ```json
  [
    {
      "id": "usr_123",
      "name": "Jane Doe",
      "email": "jane@example.com",
      "role": "owner",
      "status": "active",
      "lastActiveAt": "2023-10-01T12:00:00Z"
    },
    {
      "id": null,
      "name": null,
      "email": "pending@example.com",
      "role": "operator",
      "status": "pending",
      "lastActiveAt": null
    }
  ]
  ```
  > `status` is `"active"` or `"pending"` (invite not yet accepted). `name` and `lastActiveAt` are null for pending invites.

### `POST /workspaces/{id}/members`
- **Auth required:** Yes (Admin+)
- **Request:** `{"email": "...", "role": "operator"}`
- **Response:** `201 Created` — returns the pending member object. Sends an invite email to the address.

### `POST /workspaces/{id}/members/{member_id}/resend-invite`
- **Auth required:** Yes (Admin+)
- **Response:** `200 OK` — re-sends the invite email to a pending member.

### `PATCH /workspaces/{id}/members/{member_id}`
- **Auth required:** Yes (Admin+ for most changes; Owner-only to change another Admin's role)
- **Request:** `{"role": "admin"}`
- **Response:** `200 OK`

### `DELETE /workspaces/{id}/members/{member_id}`
- **Auth required:** Yes (Owner only)
- **Response:** `200 OK`

---

## 4. Approvals (HITL Queue)

### `GET /workspaces/{id}/approvals`
- **Auth required:** Yes (Operator+)
- **Query Params:** `?status=PENDING|APPROVED|REJECTED|EXPIRED|CANCELLED|ALL`
- **Response:**
  ```json
  [
    {
      "id": "app_123",
      "status": "PENDING",
      "riskLevel": "HIGH",
      "actionSummary": "Refund $84 — Order #4471",
      "agentName": "Action Agent",
      "conversationId": "conv_221",
      "slaExpiresAt": "2023-10-01T14:00:00Z",
      "createdAt": "2023-10-01T12:00:00Z",
      "parameters": {
        "Order ID": "#4471",
        "Amount": "$84.00",
        "Reason": "item arrived damaged",
        "Customer": "#221 (Jane K.)"
      },
      "conversationSummary": "Customer reported item damaged on arrival...",
      "resolvedAt": null,
      "resolvedBy": null,
      "rejectReason": null
    }
  ]
  ```
  > `parameters` is a `Record<string, string>` — a flat key-value map of the action's parameters, displayed verbatim in the UI.
  > `riskLevel` is `"HIGH"`, `"MED"`, or `"LOW"`.
  > `resolvedAt`, `resolvedBy` (email string), and `rejectReason` are set once resolved.

### `POST /workspaces/{id}/approvals/{app_id}/approve`
- **Auth required:** Yes (Operator+)
- **Request:** empty body
- **Response:** `200 OK`
- **Behavior:** Updates `status = "APPROVED"`, sets `resolved_at` and `resolved_by`. Resumes the paused LangGraph thread.

### `POST /workspaces/{id}/approvals/{app_id}/reject`
- **Auth required:** Yes (Operator+)
- **Request:** `{"reason": "..."}` — `reason` is required.
- **Response:** `200 OK`
- **Behavior:** Updates `status = "REJECTED"`, sets `reject_reason`. Resumes the paused LangGraph thread with the rejection.

---

## 5. Conversations

### `GET /workspaces/{id}/conversations`
- **Auth required:** Yes (Read-only+)
- **Query Params:** `?status=resolved|escalated|in_progress|ALL&search=<text>&cursor=<token>&limit=50`
  > `search` runs full-text search over customer name, customer ID, and transcript content.
- **Response:**
  ```json
  [
    {
      "id": "conv_221",
      "status": "escalated",
      "customerId": "221",
      "customerName": "Jane K.",
      "summary": "damaged item, refund request",
      "agentsInvolved": ["retrieval", "action", "escalation"],
      "lastUpdatedAt": "2023-10-01T12:00:00Z"
    }
  ]
  ```
  > `agentsInvolved` is an array of agent type strings. The frontend renders an icon per agent.

### `GET /workspaces/{id}/conversations/{conv_id}`
- **Auth required:** Yes (Read-only+)
- **Response:** Full conversation detail including ordered transcript turns.
  ```json
  {
    "id": "conv_221",
    "status": "escalated",
    "customerId": "221",
    "customerName": "Jane K.",
    "agentsInvolved": ["retrieval", "action", "escalation"],
    "createdAt": "...",
    "transcript": [
      {
        "id": "turn_1",
        "speaker": "customer",
        "text": "My order arrived damaged.",
        "timestamp": "...",
        "citations": [],
        "inlineApprovalId": null
      },
      {
        "id": "turn_4",
        "speaker": "agent",
        "text": "I can see order #4471 qualifies for a refund...",
        "timestamp": "...",
        "citations": [
          {"source": "return-policy.pdf", "chunk": "4.2", "score": 0.91}
        ],
        "inlineApprovalId": "app_123"
      }
    ]
  }
  ```
  > `citations` is only present on agent turns. `inlineApprovalId` links to the approval record triggered at that turn.

---

## 6. Knowledge Base

### `GET /workspaces/{id}/knowledge-base`
- **Auth required:** Yes (Read-only+)
- **Query Params:** `?search=<filename>&status=processing|ready|failed`
- **Response:**
  ```json
  [
    {
      "id": "doc_123",
      "filename": "return-policy.pdf",
      "status": "ready",
      "tags": {"category": "Policy", "productLine": "All"},
      "sizeBytes": 82000,
      "chunkCount": 14,
      "uploadedAt": "2023-10-01T10:00:00Z",
      "errorMessage": null
    }
  ]
  ```
  > `status` is `"processing"`, `"ready"`, or `"failed"`. The frontend polls this endpoint to update ingestion progress indicators. `errorMessage` is set when `status = "failed"`.

### `POST /workspaces/{id}/knowledge-base/upload`
- **Auth required:** Yes (Operator+)
- **Request:** `multipart/form-data` with fields:
  - `file`: the binary file
  - `tags`: JSON string e.g. `{"category": "Policy"}`
- **Response:** `202 Accepted`
  ```json
  {
    "id": "doc_456",
    "filename": "shipping.pdf",
    "status": "processing"
  }
  ```

### `DELETE /workspaces/{id}/knowledge-base/{doc_id}`
- **Auth required:** Yes (Operator+)
- **Response:** `200 OK`

### `POST /workspaces/{id}/knowledge-base/{doc_id}/retry`
- **Auth required:** Yes (Operator+)
- **Response:** `202 Accepted`
- **Behavior:** Re-triggers ingestion for a document with `status = "failed"`.

### `POST /workspaces/{id}/knowledge-base/test-retrieval`
- **Auth required:** Yes (Read-only+)
- **Request:** `{"query": "what is the return policy?"}`
- **Response:**
  ```json
  [
    {
      "documentId": "doc_123",
      "filename": "return-policy.pdf",
      "chunkIndex": 3,
      "chunkText": "Items may be returned within 30 days of delivery...",
      "score": 0.91
    }
  ]
  ```

---

## 7. Agent Configuration

### `GET /workspaces/{id}/agents`
- **Auth required:** Yes (Read-only+)
- **Response:** Object with a key per agent type plus `global`.
  ```json
  {
    "orchestrator": {
      "id": "orchestrator",
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20240620",
      "fallbackModel": "gpt-4o",
      "systemPrompt": "You are the orchestrator...",
      "tools": ["route_request", "clarify_intent"],
      "guardrails": {
        "pii": true,
        "toxicity": true,
        "promptInjection": true,
        "refundCap": null,
        "discountLimit": null
      },
      "hitlBreakpoints": [
        {
          "id": "b1",
          "label": "Low Confidence Routing",
          "expiryBehavior": "auto-escalate",
          "slaWindowMins": 30
        }
      ]
    },
    "retrieval": { ... },
    "action": { ... },
    "escalation": { ... },
    "global": { ... }
  }
  ```
  > The `apiKey` field is **never returned** in GET responses — only a masked hint (e.g., `"apiKeyHint": "sk-ant-...7890"`) is returned to confirm a key is set.

### `PATCH /workspaces/{id}/agents/{agent_type}`
- **Auth required:** Yes (Admin+)
- **Request:** Partial update of any fields for the specified agent type. `agent_type` is one of: `orchestrator`, `retrieval`, `action`, `escalation`, `global`.
  ```json
  {
    "model": "claude-3-haiku-20240307",
    "guardrails": { "refundCap": 75 }
  }
  ```
- **Response:** `200 OK` — returns the full updated agent config object.

### `PUT /workspaces/{id}/agents/{agent_type}/api-key`
- **Auth required:** Yes (Admin+)
- **Request:** `{"apiKey": "sk-ant-..."}`
- **Response:** `200 OK` — stores the key encrypted. Returns `{"apiKeyHint": "sk-ant-...xyz"}`.
  > Separate endpoint for API keys so they are never included in general PATCH payloads and are handled with extra care (encryption, audit log).

---

## 8. Agent Stats

### `GET /workspaces/{id}/stats`
- **Auth required:** Yes (Read-only+)
- **Query Params:** `?timeRange=24h|7d|30d`
- **Response:**
  ```json
  {
    "timeRange": "7d",
    "metrics": [
      { "id": "resolution", "label": "Resolution Rate", "value": "87%", "trend": { "direction": "up", "value": "2%", "isGood": true } },
      { "id": "active", "label": "Active Convos", "value": "12", "trend": null },
      { "id": "latency", "label": "Avg Latency", "value": "1.4s", "trend": { "direction": "down", "value": "0.2s", "isGood": true } },
      { "id": "guardrail", "label": "Guardrail Block Rate", "value": "2.1%", "trend": { "direction": "up", "value": "0.4%", "isGood": false } },
      { "id": "fallback", "label": "Fallback Rate", "value": "0.8%", "trend": null },
      { "id": "hitrate", "label": "Retrieval Hit Rate", "value": "91%", "trend": null }
    ],
    "timeseries": {
      "resolution": [{ "timestamp": "2023-10-01T00:00:00Z", "value": 0.85 }],
      "latencyP50": [...],
      "guardrailBlocks": [...],
      "fallbackRate": [...]
    },
    "perAgentBreakdown": [
      {
        "agentName": "Orchestrator",
        "calls": 1204,
        "avgLatency": "0.6s",
        "fallbackRate": "0.2%",
        "errorRate": "0.1%"
      },
      { "agentName": "Retrieval", "calls": 842, "avgLatency": "1.1s", "fallbackRate": "0.5%", "errorRate": "0.8%" },
      { "agentName": "Action", "calls": 310, "avgLatency": "0.9s", "fallbackRate": "0.0%", "errorRate": "0.3%" },
      { "agentName": "Escalation", "calls": 58, "avgLatency": "2.0s", "fallbackRate": "1.7%", "errorRate": "0.0%" }
    ]
  }
  ```

---

## 9. Settings — Profile

### `GET /profile`
- **Auth required:** Yes
- **Response:**
  ```json
  {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "timezone": "Africa/Nairobi",
    "avatarUrl": "https://..."
  }
  ```

### `PATCH /profile`
- **Auth required:** Yes
- **Request:** `multipart/form-data` or JSON partial update.
  - For text fields: `{"name": "...", "email": "...", "timezone": "..."}`
  - For avatar: `multipart/form-data` with `avatar` file field (JPEG/PNG/WebP, max 2MB). Backend resizes to 256×256 and stores in object storage.
- **Response:** `200 OK` — returns updated profile object.

### `POST /profile/change-password`
- **Auth required:** Yes
- **Request:** `{"currentPassword": "...", "newPassword": "..."}`
- **Response:** `200 OK`

---

## 10. Settings — Notifications

### `GET /workspaces/{id}/notifications`
- **Auth required:** Yes (Admin+)
- **Response:**
  ```json
  {
    "connectedChannels": [
      {
        "id": "ch_1",
        "type": "slack",
        "name": "Slack",
        "destination": "#support-alerts",
        "status": "connected"
      },
      {
        "id": "ch_2",
        "type": "email",
        "name": "Email",
        "destination": "ops@yourco.com",
        "status": "connected"
      }
    ],
    "availableChannels": [
      { "id": "ac1", "name": "Microsoft Teams", "icon": "teams" },
      { "id": "ac2", "name": "Discord", "icon": "discord" },
      { "id": "ac3", "name": "WhatsApp", "icon": "whatsapp" },
      { "id": "ac4", "name": "Telegram", "icon": "telegram" }
    ],
    "webhookUrl": "https://hooks.yourdomain.com/...",
    "events": {
      "newEscalation": true,
      "slaBreach": true,
      "approvalExpired": true,
      "guardrailBlock": false
    }
  }
  ```
  > `channel.status` is `"connected"` or `"error"`. `channel.type` maps to the icon shown in the UI.

### `PATCH /workspaces/{id}/notifications`
- **Auth required:** Yes (Admin+)
- **Request:** Partial update of any fields (`webhookUrl`, `events`, etc.).
- **Response:** `200 OK`

### `POST /workspaces/{id}/notifications/channels`
- **Auth required:** Yes (Admin+)
- **Request:** `{"type": "slack", "destination": "#support-alerts", "name": "Slack"}`
- **Response:** `201 Created` — returns the new connected channel object.

### `DELETE /workspaces/{id}/notifications/channels/{channel_id}`
- **Auth required:** Yes (Admin+)
- **Response:** `200 OK`

---

## 11. Settings — Billing

### `GET /workspaces/{id}/billing`
- **Auth required:** Yes (Owner only)
- **Response:**
  ```json
  {
    "planName": "Pro",
    "price": 49,
    "interval": "mo",
    "usage": {
      "conversations": 1204,
      "limit": 5000
    },
    "paymentMethods": [
      {
        "id": "pm_1",
        "type": "card",
        "label": "Card ending 4417",
        "isDefault": true
      }
    ],
    "billingDetails": {
      "address": "123 Main St, Nairobi, KE",
      "taxId": "KE-123456"
    },
    "invoices": [
      { "id": "inv_1", "date": "Sep 2026", "amount": 49.00, "status": "Paid" },
      { "id": "inv_2", "date": "Aug 2026", "amount": 49.00, "status": "Paid" }
    ]
  }
  ```
  > `paymentMethod.type` is `"card"`, `"paypal"`, `"mpesa"`, or `"bank"`. The frontend renders a different icon per type.

### `PATCH /workspaces/{id}/billing`
- **Auth required:** Yes (Owner only)
- **Request:** Partial update of `billingDetails`.
- **Response:** `200 OK`

### `POST /workspaces/{id}/billing/payment-methods`
- **Auth required:** Yes (Owner only)
- **Request:** Payment method token from the payment provider (Stripe token, etc.).
- **Response:** `201 Created`

### `DELETE /workspaces/{id}/billing/payment-methods/{pm_id}`
- **Auth required:** Yes (Owner only)
- **Response:** `200 OK`

---

## 12. Settings — Integrations

### `GET /workspaces/{id}/integrations`
- **Auth required:** Yes (Admin+)
- **Response:**
  ```json
  {
    "connected": [
      {
        "id": "int_1",
        "type": "shopify",
        "name": "Shopify",
        "status": "connected",
        "lastSyncAt": "2023-10-01T11:55:00Z"
      }
    ],
    "available": [
      { "id": "ai1", "name": "WooCommerce", "category": "E-commerce" },
      { "id": "ai2", "name": "Magento", "category": "E-commerce" },
      { "id": "ai3", "name": "Zendesk", "category": "Support/CRM" },
      { "id": "ai4", "name": "Salesforce", "category": "Support/CRM" }
    ]
  }
  ```
  > `integration.status` is `"connected"`, `"error"`, or `"disconnected"`.

### `POST /workspaces/{id}/integrations`
- **Auth required:** Yes (Admin+)
- **Request:** `{"type": "shopify", "credentials": {...}}` — credentials structure varies by integration type.
- **Response:** `201 Created`

### `DELETE /workspaces/{id}/integrations/{integration_id}`
- **Auth required:** Yes (Admin+)
- **Response:** `200 OK`

### `POST /workspaces/{id}/integrations/custom`
- **Auth required:** Yes (Admin+)
- **Request:** MCP adapter connection config (format TBD with backend team).
- **Response:** `201 Created`
  > Supports the "Add custom connector" flow shown in the UI (connects an in-house database or third-party platform via the universal MCP adapter).

---

## 13. Homepage Summary

The homepage needs a single aggregated endpoint to avoid multiple parallel fetches on load.

### `GET /workspaces/{id}/summary`
- **Auth required:** Yes (Read-only+)
- **Response:**
  ```json
  {
    "pendingApprovals": [
      {
        "id": "app_123",
        "summary": "Refund $84 — order #4471",
        "riskLevel": "HIGH",
        "slaExpiresAt": "2023-10-01T14:04:00Z"
      }
    ],
    "pendingApprovalCount": 3,
    "stats": {
      "resolutionRate": "87%",
      "activeConversations": 12,
      "avgLatency": "1.4s",
      "guardrailBlockRate": "2.1%"
    },
    "systemHealth": [
      { "label": "Shopify adapter", "ok": true },
      { "label": "Orchestrator", "ok": true },
      { "label": "Retrieval Agent", "ok": true },
      { "label": "Action Agent", "ok": true },
      { "label": "Escalation Agent", "ok": true }
    ],
    "recentConversations": [
      {
        "id": "conv_221",
        "status": "escalated",
        "summary": "damaged item, refund request"
      }
    ]
  }
  ```
  > Returns the top 3 most urgent pending approvals, 4 headline stats, integration health statuses, and the 3 most recent conversations. Full data lives in the respective domain endpoints.

---

## 14. Providers & API Keys

These endpoints support the Agent Configuration "Model & Keys" tab, which allows per-agent provider and model selection.

### `GET /workspaces/{id}/providers`
- **Auth required:** Yes (Admin+)
- **Response:**
  ```json
  [
    {
      "id": "anthropic",
      "name": "Anthropic",
      "isVerified": true,
      "apiKeyHint": "sk-ant-...7890",
      "models": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307", "claude-3-opus-20240229"]
    },
    {
      "id": "openai",
      "name": "OpenAI",
      "isVerified": false,
      "apiKeyHint": null,
      "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
    },
    {
      "id": "ollama",
      "name": "Ollama (Local)",
      "isVerified": true,
      "apiKeyHint": null,
      "models": ["llama3", "mistral", "phi3"]
    }
  ]
  ```
  > `apiKeyHint` shows the last 4 chars of a set key. `isVerified` confirms the key passed a test call. Ollama requires no key.

### `PUT /workspaces/{id}/providers/{provider_id}/api-key`
- **Auth required:** Yes (Admin+)
- **Request:** `{"apiKey": "sk-ant-..."}`
- **Response:** `200 OK` — stores encrypted. Returns `{"apiKeyHint": "sk-ant-...7890"}`.

### `POST /workspaces/{id}/providers/{provider_id}/verify`
- **Auth required:** Yes (Admin+)
- **Response:** `200 OK` or `400` if the key is invalid.
- **Behavior:** Makes a lightweight test call to the provider API, sets `is_verified = true` on success.

### `DELETE /workspaces/{id}/providers/{provider_id}/api-key`
- **Auth required:** Yes (Admin+)
- **Response:** `200 OK`
- **Behavior:** Blocked if this is the `active_provider` for the workspace.

---

## 15. Standard Error Responses

All errors return the following shape:

```json
{
  "error": "error_code_snake_case",
  "message": "Human-readable description for display."
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Bad request — invalid input (e.g., wrong password, missing required field) |
| `401` | Unauthenticated — missing or expired access token |
| `403` | Forbidden — authenticated but insufficient role |
| `404` | Resource not found |
| `409` | Conflict — e.g., email already exists on signup |
| `422` | Validation error — e.g., model does not belong to the active provider |
| `429` | Rate limited |
| `500` | Internal server error |
