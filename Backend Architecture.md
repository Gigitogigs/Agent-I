# Agent-I Backend Architecture

This document defines the backend architecture required to support the Agent-I frontend API contract. It outlines the core subsystems, database schema requirements, and data flow for a multi-tenant, agentic support platform.

## 1. System Overview

The backend will transition from a single-tenant local tool to a multi-tenant SaaS architecture. All resources (agents, conversations, knowledge base documents, approvals) will be scoped to a **Workspace**.

**Core Components:**
- **FastAPI Application (Gateway & API):** Handles all REST endpoints defined in the API contract. Manages authentication, workspace routing, and delegates to the LangGraph agents.
- **LangGraph Orchestrator:** The core agent logic. Runs asynchronously. State is persisted per-conversation using a Postgres checkpointer.
- **PostgreSQL Database:** The single source of truth for relational data (users, workspaces, billing) and vector data (pgvector for the knowledge base).
- **Redis:** Used for caching, rate limiting, and managing background task queues (e.g., document processing for the knowledge base).

---

## 2. Multi-Tenancy & Data Isolation

Data isolation is critical. All database queries must be scoped by `workspace_id`.
We will enforce this using **Postgres Row-Level Security (RLS)** to guarantee that a user from Workspace A cannot access records from Workspace B, even if the application code has a bug.

### 2.1 Core Entities
- **User:** Represents a human (operator, admin). Has a unique ID, email, and password hash.
- **Workspace:** The tenant boundary. Contains its own agents, knowledge base, and conversations.
- **WorkspaceMember:** A join table linking Users to Workspaces with specific roles (`owner`, `admin`, `operator`, `read-only`).

---

## 3. Authentication & Authorization

### 3.1 Token Strategy: JWT via HTTP-only Cookies

We will use **JWT (JSON Web Tokens)** delivered in **HTTP-only cookies**. This satisfies the frontend contract's note about session-based or Bearer token auth while being more secure than storing tokens in `localStorage`.

**Token types:**
- **Access Token:** Short-lived (15 min). Carries `user_id`, `email`, and the user's workspace memberships. Verified on every authenticated request.
- **Refresh Token:** Long-lived (7 days). Stored in the DB (`user_sessions` table). Used to issue a new access token without re-login.

**Session & Password Lifecycle:**
1. `POST /auth/login` → validates credentials → issues access + refresh tokens as HTTP-only cookies.
2. Client makes requests with cookies automatically attached.
3. On access token expiry → client calls `POST /auth/refresh` → server validates refresh token from DB → issues new access token.
4. `POST /auth/logout` → server deletes the `user_sessions` row → both cookies cleared.
5. **Password Reset:** `POST /auth/forgot-password` generates a secure token stored in `users.reset_password_token` (with expiry). `POST /auth/reset-password` validates the token and updates the password hash.

**User Deletion / Workspace Deletion (48-hour grace period):**
- On `DELETE /account` or `DELETE /workspaces/{id}`: a `scheduled_for_deletion_at` timestamp is set on the record.
- A background job runs periodically to hard-delete records where the grace period has elapsed.
- All active sessions for a deleted user are immediately invalidated.
- `POST /workspaces/{id}/cancel-deletion` clears the timestamp.

---

### 3.2 Role-Based Access Control (RBAC)

Roles are scoped **per workspace** via the `workspace_members` join table. A single user can be an `admin` in Workspace A and an `operator` in Workspace B simultaneously.

| Role | Description |
|------|-------------|
| `owner` | Created when workspace is first created. Full control including billing and workspace deletion. Only one owner per workspace. |
| `admin` | Can manage members, agent config, and the knowledge base. Cannot delete the workspace or access billing. |
| `operator` | Can view and act on approvals (approve/reject), view conversations. Cannot change system configuration. |
| `read-only` | Can view stats, conversations, and approval history. Cannot take any action. |

**Endpoint Permission Matrix:**

| Endpoint | `owner` | `admin` | `operator` | `read-only` |
|---|---|---|---|---|
| `GET /workspaces/{id}/members` | ✅ | ✅ | ❌ | ❌ |
| `POST /workspaces/{id}/members` | ✅ | ✅ | ❌ | ❌ |
| `PATCH /workspaces/{id}/members/{id}` | ✅ | ✅ | ❌ | ❌ |
| `DELETE /workspaces/{id}/members/{id}` | ✅ | ❌ | ❌ | ❌ |
| `GET /workspaces/{id}/approvals` | ✅ | ✅ | ✅ | ✅ |
| `POST /workspaces/{id}/approvals/{id}/approve` | ✅ | ✅ | ✅ | ❌ |
| `POST /workspaces/{id}/approvals/{id}/reject` | ✅ | ✅ | ✅ | ❌ |
| `GET /workspaces/{id}/conversations` | ✅ | ✅ | ✅ | ✅ |
| `GET /workspaces/{id}/knowledge-base` | ✅ | ✅ | ✅ | ✅ |
| `POST /workspaces/{id}/knowledge-base/upload` | ✅ | ✅ | ❌ | ❌ |
| `PATCH /workspaces/{id}/agents/{type}` | ✅ | ✅ | ❌ | ❌ |
| `GET /workspaces/{id}/stats` | ✅ | ✅ | ✅ | ✅ |
| `GET /workspaces/{id}/billing` | ✅ | ❌ | ❌ | ❌ |
| `DELETE /workspaces/{id}` | ✅ | ❌ | ❌ | ❌ |

**Approval-level RBAC:** For HITL approvals involving elevated risk (e.g., `HIGH` risk refunds), the `reviewer_role` field on the `approval_requests` record restricts which role can act — enforced both at the API layer and via Postgres RLS.

---

### 3.3 FastAPI Implementation

Auth will be handled via **FastAPI dependency injection**. A `get_current_user` dependency will be applied globally or per-router, making it impossible to add a new route and accidentally forget auth.

```python
# backend/api/dependencies.py

async def get_current_user(token: str = Depends(cookie_scheme), db = Depends(get_db)) -> User:
    """Decode JWT, validate, return user. Raises 401 on failure."""
    ...

async def require_workspace_role(min_role: Role):
    """Factory dependency. Verifies user is a member of the workspace in the path
    and has at least the specified role. Raises 403 otherwise."""
    ...
```

Usage in a router:
```python
@router.post("/{ws_id}/approvals/{app_id}/approve")
async def approve(
    ws_id: str,
    app_id: str,
    user: User = Depends(require_workspace_role(Role.OPERATOR)),
    db = Depends(get_db),
):
    ...
```



---

## 4. API Subsystems

### 4.1 Approvals (HITL Queue)
- **Database:** `approval_requests` table with a `workspace_id`.
- **Workflow:** When a subagent flags an action, a record is created. The operator approves/rejects via the API. The backend atomically updates the record and resumes the LangGraph graph using Redis pub/sub.

### 4.2 Conversations (Chat API)
- **Database:** `conversations` table linked to `workspace_id`.
- **Workflow:** When a conversation starts, a LangGraph thread is initialized. The `GET /workspaces/{id}/conversations/{conv_id}` endpoint reads the LangGraph checkpointer state to return the transcript. Real-time chat (if implemented) will use WebSockets.

### 4.3 File Uploads

The system handles two distinct categories of file uploads, each with different processing pipelines and storage rules.

#### 4.3.1 Knowledge Base Documents
- **Accepted types:** PDF, DOCX, TXT, MD
- **Upload endpoint:** `POST /workspaces/{id}/knowledge-base/upload` (`multipart/form-data`)
- **Storage:** Raw files saved to object storage (local filesystem for dev, MinIO/S3-compatible for production). The file path is stored on the `documents` metadata record.
- **Processing pipeline (async via Document Ingestion Worker):**
  1. File saved to object storage → `documents.status = 'processing'`.
  2. Worker picks up job from Redis queue.
  3. Text extracted, chunked (semantic, 400–800 tokens with overlap), embedded via the configured embedding model.
  4. Chunks upserted to `document_chunks` table with pgvector embeddings, scoped to `workspace_id`.
  5. `documents.status` set to `'ready'` on success or `'failed'` on error.
- **Frontend polling:** `GET /workspaces/{id}/knowledge-base` returns the current `status` per document so the UI can show a progress indicator.
- **Retrieval testing:** `POST /workspaces/{id}/knowledge-base/test-retrieval` runs a pgvector similarity search scoped to `workspace_id` and returns the top-k matching chunks.

#### 4.3.2 User Profile Avatars
- **Upload endpoint:** `PATCH /profile` with `multipart/form-data` (alongside other profile fields)
- **Storage:** Object storage, under a per-user path (e.g. `avatars/{user_id}/avatar.webp`). The URL is stored on the `users.avatar_url` column.
- **Processing:** No async pipeline needed. On upload:
  1. Validate file type (JPEG, PNG, WebP only) and size limit (e.g. ≤ 2 MB).
  2. Resize/compress to a standard dimension (e.g. 256×256 px) server-side.
  3. Save to object storage, overwriting any previous avatar.
  4. Update `users.avatar_url` and return the new URL in the response.
- **No background job required** — avatar processing is fast enough to handle synchronously in the request.

### 4.4 Agent Configuration

Agent configuration is migrating from static YAML (`subagent_registry.yaml`) to the Postgres database, scoped per workspace. This enables per-workspace model selection from the frontend while the `model_factory.py` harness — which already supports all 8 providers — remains the single execution point.

---

#### 4.4.1 Design Constraints

1. **Provider lock-in per workspace:** All agents in a workspace must use the same provider. A workspace cannot mix Claude for the Orchestrator and Gemini for the Action Agent. This prevents incompatible tool-calling behaviors and simplifies API key management.
2. **Provider determined by loaded API keys:** The providers available to a workspace are restricted to only those for which a valid API key has been configured.
3. **Two configuration modes:**
   - **Global:** One model is applied uniformly to all agents in the workspace.
   - **Custom:** Each agent gets its own model, but all models must come from the workspace's active provider.
4. **Ollama is always available** as a zero-key provider (local models). It does not require an API key entry.

---

#### 4.4.2 Database Schema

```sql
-- Stores encrypted API keys per provider per workspace.
-- A workspace can hold keys for multiple providers, but only one can be 'active'.
CREATE TABLE workspace_provider_keys (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider         TEXT NOT NULL,  -- 'anthropic' | 'openai' | 'google-genai' | 'groq' | 'aws' | 'nvidia' | 'huggingface'
    encrypted_api_key TEXT NOT NULL, -- AES-256 encrypted at rest
    is_verified      BOOLEAN DEFAULT FALSE, -- set to TRUE after a successful test call
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, provider)
);

-- Stores the active agent model configuration for a workspace.
CREATE TABLE workspace_agent_config (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    active_provider  TEXT NOT NULL,  -- the locked-in provider; all models must come from here
    mode             TEXT NOT NULL DEFAULT 'global', -- 'global' | 'custom'
    global_model     TEXT,           -- used when mode = 'global'
    custom_models    JSONB,          -- used when mode = 'custom'
                                     -- e.g. {"orchestrator": "claude-3-5-sonnet-20241022",
                                     --        "retrieval_agent": "claude-3-haiku-20240307",
                                     --        "action_agent":    "claude-3-haiku-20240307",
                                     --        "escalation_agent":"claude-3-haiku-20240307"}
    global_temperature    FLOAT DEFAULT 0.7,  -- used when mode = 'global'
    custom_temperatures   JSONB,              -- used when mode = 'custom'
                                              -- e.g. {"orchestrator": 1.0, "retrieval_agent": 0.7}
    global_system_prompt  TEXT,          -- used when mode = 'global'; auto-propagated to all agents
    custom_prompts        JSONB,         -- used when mode = 'custom'; per-agent system prompt overrides
                                         -- e.g. {"orchestrator":    "You are a senior support agent...",
                                         --        "retrieval_agent": "You are a retrieval specialist...",
                                         --        "action_agent":    "You execute verified actions...",
                                         --        "escalation_agent":"You prepare escalation summaries..."}
                                         -- NULL entries fall back to the built-in default prompt for that agent.

    custom_tools            JSONB, -- e.g. {"orchestrator": ["route_request"], "action_agent": ["issue_refund", "cancel_order"]}
    custom_guardrails       JSONB, -- e.g. {"action_agent": {"pii": true, "refundCap": 50}}
    custom_hitl_breakpoints JSONB, -- e.g. {"action_agent": [{"id": "b2", "label": "Refund Exceeds Cap", "expiryBehavior": "auto-reject", "slaWindowMins": 60}]}
    
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id)
);
```

---

#### 4.4.3 API Endpoints

The existing API contract section 7 covers agent config. We also need provider key management:

| Method | Endpoint | Role Required | Description |
|--------|----------|---------------|-------------|
| `GET` | `/workspaces/{id}/agents` | `operator` | Returns active config: mode, provider, model(s), per-agent breakdown |
| `PATCH` | `/workspaces/{id}/agents` | `admin` | Update mode (`global`/`custom`), global model, or per-agent models |
| `GET` | `/workspaces/{id}/providers` | `admin` | Lists configured providers and their verification status |
| `POST` | `/workspaces/{id}/providers` | `admin` | Add or update an API key for a provider |
| `DELETE` | `/workspaces/{id}/providers/{provider}` | `admin` | Remove a provider key (blocked if it's the active provider) |
| `POST` | `/workspaces/{id}/providers/{provider}/verify` | `admin` | Test the key with a lightweight API call and mark `is_verified = TRUE` |

**`GET /workspaces/{id}/agents` Response shape:**
```json
{
  "active_provider": "anthropic",
  "mode": "custom",
  "available_providers": ["anthropic", "ollama"],
  "global_model": null,
  "global_system_prompt": null,
  "agents": {
    "orchestrator":    { "model": "claude-3-5-sonnet-20241022", "temperature": 1.0, "system_prompt": "You are a senior support agent..." },
    "retrieval_agent": { "model": "claude-3-haiku-20240307",    "temperature": 0.7, "system_prompt": null },
    "action_agent":    { "model": "claude-3-haiku-20240307",    "temperature": 0.7, "system_prompt": null },
    "escalation_agent":{ "model": "claude-3-haiku-20240307",    "temperature": 0.7, "system_prompt": null }
  }
}
```

---

#### 4.4.4 Enforcement Logic (Same-Provider Constraint)

When a `PATCH /workspaces/{id}/agents` request arrives:

1. Resolve the workspace's `active_provider` from `workspace_agent_config`.
2. For every model name submitted (whether in `global_model` or `custom_models`):
   - Look it up in a backend-maintained provider→models catalogue.
   - If any model does not belong to `active_provider` → return `422 Unprocessable Entity` with a clear message.
3. If `mode = custom`, also verify that **all 4 agents** have an explicit model entry — no agent may be left without a model.
4. If the user is trying to switch `active_provider` (e.g. switching from Anthropic to OpenAI):
   - Verify the new provider has a valid, verified key in `workspace_provider_keys`.
   - Reset all custom models to null (they are now invalid for the new provider).
   - Return the available models for the new provider in the response.

---

#### 4.4.5 Runtime Integration (`model_factory.py`)

The `build_model()` function currently reads from `subagent_registry.yaml`. It will be updated to accept a config dict fetched from the database instead:

```python
# harness/model_factory.py  (updated flow)

def build_model(agent_config: dict, api_key: str | None = None):
    """
    agent_config is now sourced from workspace_agent_config (DB),
    not from subagent_registry.yaml.
    api_key is the decrypted key for the workspace's active provider,
    injected by the backend — never stored in the LLM context.
    """
    provider = agent_config["provider"]
    model_class = PROVIDERS[provider]
    kwargs = { "model": agent_config["model"], "temperature": agent_config.get("temperature", 0.7) }
    if api_key:
        kwargs["api_key"] = api_key  # injected securely; never in LLM prompt
    return model_class(**kwargs)
```

The Orchestrator graph fetches the workspace config once at the start of each conversation turn and passes the resolved `agent_config` dicts down to subagents — no subagent opens a DB connection or reads a YAML file on its own.



### 4.5 Agent Stats
- **Database:** Aggregation queries over `conversations`, `conversation_turns`, and `approval_requests` tables.
- **Workflow:** `GET /workspaces/{id}/stats` computes resolution rates, latency, guardrail blocks, and per-agent breakdowns. Results for larger time ranges (7d/30d) should be cached in Redis to reduce database load.

### 4.6 Settings — Notifications
- **Database:** `workspace_notification_channels` (stores Slack webhooks, email destinations) and `workspace_notification_settings` (event toggles).
- **Workflow:** The UI configures webhooks and event toggles (e.g., SLA breach, new escalation). The background Notification Worker (Section 9.2) reads these settings before dispatching alerts.

### 4.7 Settings — Billing
- **Database:** `workspaces` table stores subscription tier, usage limits, and Stripe customer ID.
- **Workflow:** `GET /workspaces/{id}/billing` interfaces with a mock (or Stripe) backend to return plan details, usage metrics against limits, and invoice history.

### 4.8 Settings — Integrations
- **Database:** `workspace_integrations` stores encrypted credentials (e.g., Shopify tokens, Zendesk API keys) and connection status.
- **Workflow:** Endpoints like `POST /workspaces/{id}/integrations/custom` securely store MCP adapter connection configs, which the Action Agent will use at runtime.

### 4.9 Homepage Summary
- **Workflow:** `GET /workspaces/{id}/summary` acts as a composite endpoint (BFF pattern). It runs 4 parallel optimized queries to fetch: top 3 urgent pending approvals, headline stats, recent conversations, and system health status. This prevents the frontend from needing to make 4 separate blocking HTTP requests on initial load.

---

## 5. Security & Secrets Management
- Agent API keys (e.g., OpenAI, Anthropic) configured per workspace must be encrypted at rest in the database.
- The Guardrail Layer will continue to sanitize inputs and outputs before they hit the LLMs or external tools.

---

## 6. Backend File Structure

To support the new API layer and multi-tenancy, the codebase will be structured as follows:

```text
support-system/
├── backend/                  # The new unified FastAPI Application (Gateway)
│   ├── api/                  # REST API Endpoints
│   │   ├── routers/
│   │   │   ├── auth.py       # POST /auth/login, /auth/signup
│   │   │   ├── workspaces.py # Workspace & Member CRUD
│   │   │   ├── approvals.py  # HITL Approval endpoints
│   │   │   ├── chat.py       # Conversations & WS streaming
│   │   │   ├── agents.py     # Agent Configuration CRUD
│   │   │   └── knowledge.py  # Document upload & RAG testing
│   │   ├── dependencies.py   # Auth extraction, get_db, get_current_user
│   │   └── schemas.py        # Pydantic models for API Requests/Responses
│   ├── core/                 # App-wide settings and security
│   │   ├── config.py         # Env vars & global settings
│   │   └── security.py       # Password hashing, JWT creation/validation
│   ├── db/                   # Postgres Database logic
│   │   ├── models/           # SQLAlchemy/SQLModel definitions (Users, Workspaces)
│   │   ├── session.py        # Connection pooling
│   │   └── migrations/       # Alembic migrations for DB schema updates
│   └── main.py               # FastAPI entry point
├── root_agent/               # LangGraph Orchestrator (modified to require workspace_id)
├── subagents/                # Retrieval, Action, Escalation agents
├── mcp_servers/              # MCP Tool Adapters (Inventory, Orders)
├── memory/                   # Postgres checkpointer & store logic
├── guardrails/               # Security and policy enforcement
└── docker-compose.yml        # Services: web (FastAPI), postgres, redis, langfuse
```

---

## 7. Database Connection Pooling

Currently, agents and the memory checkpointer instantiate independent database pools (e.g., `psycopg2.pool`, `psycopg_pool.ConnectionPool`). 

To prevent connection exhaustion and centralize database configuration, ownership of the connection pool will be transferred to the unified **Backend Application** (`backend/db/session.py`).

**Workflow:**
- The FastAPI application manages a single, unified asynchronous connection pool bound to the application's lifecycle.
- The FastAPI application manages a single, unified asynchronous connection pool bound to the application's lifecycle.
- When an API request invokes the LangGraph Orchestrator or a specific agent, the backend passes an active database session or the unified pool reference down to the agent, eliminating the need for internal agent connection pooling.

---

## 8. Deletion Sequences

Both workspace and account deletion use a **soft-delete / grace period pattern** — no data is permanently destroyed until 48 hours have elapsed. Both share the same background job mechanism.

### 8.1 Workspace Deletion

**Trigger:** Owner clicks "Delete workspace", enters password, and confirms.

**Step 1 — `DELETE /workspaces/{id}`**
- Verify requesting user is the `owner` role → `403` otherwise.
- Verify password against `password_hash` → `400` if incorrect.
- Set `workspaces.deletion_scheduled_at = NOW()`. **No data is deleted yet.**
- Enqueue a confirmation email background job.
- Return `202 Accepted`.

**Step 2 — Login / Dashboard Check**
- On every login or dashboard load, backend checks if the active workspace has `deletion_scheduled_at` set.
- If set and within 48 hours → include `workspace_deletion_status: "grace_period"` in the response.
- Frontend renders a takeover screen: non-owners see a blocked message; the owner sees a "Cancel Deletion & Restore" button.

**Step 3 — Cancel: `POST /workspaces/{id}/cancel-deletion`**
- Sets `workspaces.deletion_scheduled_at = NULL`.
- All members regain normal access on their next request.

**Step 4 — Background Job (runs every hour)**
- Finds workspaces where `deletion_scheduled_at IS NOT NULL AND NOW() > deletion_scheduled_at + INTERVAL '48 hours'`.
- For each qualifying workspace, execute inside a **single DB transaction** in this explicit order:
  1. Delete `document_chunks` for the workspace.
  2. Delete `documents` records + remove S3/object-storage files.
  3. Delete `conversation_turns`.
  4. Delete `conversations`.
  5. Delete `approval_requests`.
  6. Delete `workspace_members`.
  7. Delete the `workspaces` record itself.
- Log the `workspace_id` to the audit log **before** deletion begins.

---

### 8.2 Account Deletion

**Trigger:** User clicks "Delete account", optionally transfers workspace ownership, enters password, and confirms. Ownership transfer is frontend-gated only — no backend endpoint required for that step.

**Step 1 — `DELETE /account`**
- Verify password against `password_hash` → `400` if incorrect.
- Set `users.deletion_scheduled_at = NOW()`.
- For **every workspace this user owns**, also set `workspaces.deletion_scheduled_at = NOW()` (cascades workspace deletion through the same mechanism).
- **Immediately invalidate all active sessions** — blocklist all refresh tokens in Redis/DB.
- Enqueue a confirmation email background job.
- Return `202 Accepted`.

**Step 2 — Login Check (during grace period)**
- If a user tries to log back in: authenticate normally but check `users.deletion_scheduled_at`.
- If set and within 48 hours → return `account_deletion_status: "grace_period"` in the login response.
- Frontend shows a takeover screen with a "Cancel Deletion & Restore Account" button.

**Step 3 — Cancel: `POST /account/cancel-deletion`**
- Sets `users.deletion_scheduled_at = NULL`.
- Sets `workspaces.deletion_scheduled_at = NULL` for **all workspaces this user owns**.
- User and all workspace members regain normal access immediately.

**Step 4 — Background Job (same hourly job)**
- Finds users where `deletion_scheduled_at IS NOT NULL AND NOW() > deletion_scheduled_at + INTERVAL '48 hours'`.
- For each qualifying user:
  1. Run the full **Workspace Deletion (Step 4)** sequence for every workspace they own.
  2. Delete all `workspace_members` rows where this user was a member (not owner) in other workspaces.
  3. Delete the `users` record itself.

---

### 8.3 Shared Rules

| Rule | Detail |
|---|---|
| **Password required** | Both flows require password re-entry. The backend must validate this — the frontend cannot be trusted alone. |
| **48-hour grace window** | Calculated as `deletion_scheduled_at + INTERVAL '48 hours'`. The hourly background job enforces the cutoff. |
| **No immediate hard delete** | Neither endpoint deletes data. Both return `202 Accepted` and defer to the background job. |
| **Cancellation is a NULL** | Restoring is simply setting the timestamp back to `NULL`. No separate restore table needed. |
| **Email on schedule** | Confirmation email sent when deletion is *scheduled*, not when it permanently executes. |
| **Email is backend-only** | Frontend has no part in sending emails. Backend enqueues this as a background job. |
| **Session invalidation on account delete** | Unlike workspace deletion, account deletion immediately invalidates all sessions — the user cannot continue to act during the grace period. |

---

### 8.4 Required DB Schema Fields

```sql
-- Users table
ALTER TABLE users ADD COLUMN deletion_scheduled_at TIMESTAMPTZ NULL;

-- Workspaces table
ALTER TABLE workspaces ADD COLUMN deletion_scheduled_at TIMESTAMPTZ NULL;

-- Index for efficient background job queries
CREATE INDEX idx_users_deletion ON users (deletion_scheduled_at) WHERE deletion_scheduled_at IS NOT NULL;
CREATE INDEX idx_workspaces_deletion ON workspaces (deletion_scheduled_at) WHERE deletion_scheduled_at IS NOT NULL;
```

---

## 9. Background Processes

The system has two distinct process types: **Queue Workers** (event-driven, consume jobs pushed to Redis) and **Scheduled Jobs** (time-driven, run on a fixed interval). Both run as separate processes/containers so their failures never block the live API or agent request path.

---

### 9.1 Process Overview

| Process | Type | Trigger | Current State |
|---|---|---|---|
| Notification Worker | Queue Worker | Redis `BRPOP` on job queue | ✅ Exists (`slack_notification_worker.py`) |
| SLA Expiry Worker | Queue Worker | Redis `BRPOP` on job queue | 🔲 Planned (`queues.py` defines the job type) |
| Session Cleanup Worker | Queue Worker | Redis `BRPOP` on job queue | 🔲 Planned (`queues.py` defines the job type) |
| Document Ingestion Worker | Queue Worker | Redis `BRPOP` on upload queue | 🔲 Needed (Knowledge Base API) |
| Deletion Cleanup Job | Scheduled (hourly) | Cron / `APScheduler` | 🔲 Needed (Section 8) |
| Email Job Worker | Queue Worker | Redis `BRPOP` on email queue | 🔲 Needed (account/workspace deletion flows) |

---

### 9.2 Queue Workers (Redis-backed)

All queue workers use Redis `BRPOP` (blocking pop) — they block and wait for a job, process it, then loop. A failure causes a sleep-and-retry to avoid tight crash loops.

#### **Notification Worker** (`notifications/slack_notification_worker.py`)
- **Queue:** `operator_notifications`
- **Trigger:** Escalation agent pushes a job when a new HITL checkpoint is created.
- **Job Payload:** `{ session_id, checkpoint_id, risk_level, action_summary, expires_at }`
- **Behavior:** Sends a Slack webhook notification. Falls back to email on Slack failure. Logs both attempt and outcome.
- **Failure handling:** On exception, sleeps 5 seconds and retries. Does not crash the process.

#### **SLA Expiry Worker**
- **Queue:** `sla_expiry_jobs`
- **Trigger:** Escalation agent enqueues a delayed job at checkpoint creation time, set to fire at `expires_at`.
- **Job Payload:** `{ checkpoint_id, session_id, expiry_policy }`
- **Behavior:** Sets the checkpoint `status = expired` in Postgres. Publishes a Redis resume signal so the Orchestrator applies the configured auto-escalation outcome (`Command(resume={"status": "expired"})`).
- **Note:** This is currently defined in `backend/queues.py` but not yet implemented.

#### **Session Cleanup Worker**
- **Queue:** `session_cleanup_jobs`
- **Trigger:** Conversation end or timeout event.
- **Job Payload:** `{ session_id }`
- **Behavior:** Flushes the session hot cache from Redis. Triggers the end-of-conversation long-term memory write to Postgres.
- **Note:** Currently defined in `backend/queues.py` as optional/future.

#### **Document Ingestion Worker**
- **Queue:** `document_ingestion_jobs`
- **Trigger:** Enqueued by `POST /workspaces/{id}/knowledge-base/upload` after saving the raw file.
- **Job Payload:** `{ document_id, workspace_id, file_path, tags }`
- **Behavior:**
  1. Loads the raw file from object storage.
  2. Chunks text (semantic/recursive chunking, 400–800 tokens with overlap).
  3. Calls the embedding model to generate vectors.
  4. Upserts chunks into `document_chunks` table with `pgvector` embeddings.
  5. Sets `documents.status = "ready"` (or `"failed"` on error).
- **Failure handling:** On fatal error, sets `status = "failed"` and logs the error. The frontend polls `GET /knowledge-base` to show current status.

#### **Email Job Worker**
- **Queue:** `email_jobs`
- **Trigger:** Any backend operation that requires sending a transactional email (deletion scheduled, invite sent, etc.).
- **Job Payload:** `{ to, template_id, template_vars }`
- **Behavior:** Calls the configured email provider (e.g., SMTP, SendGrid, Postmark). Logs delivery status.
- **Failure handling:** Retries up to 3 times with exponential backoff. Logs permanent failures to the audit log.

---

### 9.3 Scheduled Jobs (Cron / APScheduler)

These run on a fixed interval, independent of incoming requests. They will be managed by `APScheduler` running inside the main FastAPI process on startup (simple), or as a separate dedicated container for larger deployments.

#### **Deletion Cleanup Job** (every hour)
- **Scope:** Covers both workspace and account deletion (see Section 8).
- **Logic:**
  1. Query workspaces where `deletion_scheduled_at + INTERVAL '48 hours' < NOW()`.
  2. For each: run the ordered workspace deletion transaction (Section 8.1, Step 4).
  3. Query users where `deletion_scheduled_at + INTERVAL '48 hours' < NOW()`.
  4. For each: cascade through owned workspaces, then delete the user record.
- **Safety:** Each deletion runs in its own DB transaction. A failure on one workspace/user does not block others — errors are logged and retried on the next hourly run.

---

### 9.4 Redis Pub/Sub (Not a Worker — Direct Signal)

Separate from the job queues, Redis pub/sub is used for one critical real-time path:

**HITL Graph Resume**
- **Channel:** `hitl_resume:{session_id}`
- **Publisher:** `POST /workspaces/{id}/approvals/{app_id}/decide` — publishes the operator decision payload immediately after the DB update commits.
- **Subscriber:** The Agent Runtime Worker that holds the paused LangGraph execution subscribes to this channel and calls `graph.invoke(Command(resume=decision))` to continue the conversation.
- **Why pub/sub instead of a queue:** Resume must happen immediately and target a specific waiting graph instance. A queue would deliver to an arbitrary worker; pub/sub targets the subscriber holding that specific session's state.

---

### 9.5 Process Deployment

In the `docker-compose.yml`, each long-running worker will be a separate service pointing to the same codebase:

```yaml
services:
  api:         # FastAPI — handles all HTTP/WS requests
  worker:      # Combined Redis queue worker (notification, SLA, session, ingestion, email)
  scheduler:   # APScheduler process — runs hourly deletion cleanup job
  postgres:
  redis:
  langfuse:
```

For larger deployments, the combined `worker` service can be split into individual containers per job type to allow independent scaling (e.g., scale up `ingestion` workers independently during bulk KB uploads without spinning up more notification workers).


