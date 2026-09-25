# Agent-I Pre-Production Review

## Executive Summary
**What's done well:**
- The multi-agent architecture is clean and stateless. Subagents operate independently and the orchestrator manages flow, minimizing failure domains.
- API structure and dependency injection for auth/RBAC is well-organized and modular.
- Background task offloading (ARQ) for heavy tasks (LangGraph execution, document indexing) prevents API blocking and ensures scalable performance.
- Secret masking on APIs is explicitly enforced (e.g., `IntegrationOut` drops the credentials `config` field).
- State checkpointing uses LangGraph's PostgresSaver, ensuring conversation state survives server restarts.
- **Auth Integrity:** Passwords use bcrypt, refresh tokens and reset tokens are securely hashed (SHA256) in the database before storage, preventing database leak exploitation.
- **Backend Adapter Pattern:** The MCP adapter architecture uses strict `Pydantic` schemas (`OrderStatusResult`, `RefundResult`), successfully shielding the LLM from backend-specific JSON shapes.

**Summary Table**

| Severity | Issue | Location |
|---|---|---|
| Blocker | Approvals API does not enforce `reviewer_role` | `backend/api/routers/approvals.py:34` |
| Blocker | Psycopg3 `autocommit` conflict crashes agent | `support_system/subagents/action_agent/graph.py:104` |
| Blocker | Missing `executed_actions` table crashes agent | `support_system/subagents/action_agent/graph.py:84` |
| Blocker | Failed agent actions are silently skipped on retry | `support_system/subagents/action_agent/graph.py:92` |
| Blocker | Postgres superuser bypasses RLS and context is unset | `backend/core/config.py:9` |
| Blocker | `rag.resolved_tickets` missing `workspace_id` | `schema.sql:169` |
| Blocker | Path Traversal in Document Uploads | `backend/api/routers/knowledge.py:86` |
| Blocker | Broken CORS Configuration | `backend/main.py:41` |
| Blocker | Alembic/SQL Migration Desync (Data Loss Risk) | `alembic/versions/283d6e9fdee8...` |

---

## Detailed Findings

*(...Previous Sections Omitted for Brevity...)*

---

## Memory & Privacy Review

An audit of both short-term (conversation) and long-term (customer facts) memory reveals significant cost and privacy concerns. 

### 1. Long-Term Memory is "Just a Claim"
- **The Issue:** The architecture explicitly defines a `load_memory` node in `root_agent/graph.py` which attempts to read customer facts from a persistent LangGraph `BaseStore` using `user_id`. However, **the write side is completely unimplemented**. There are no tools or functions anywhere in the codebase that call `store.put()`.
- **The Secondary Flaw:** Even the read side is broken. `chat_service.py` never passes `user_id` into the `AgentState` when invoking the graph. Thus, `load_memory` silently fails on every request and always returns an empty dictionary.
- **Outcome:** Malicious documents cannot poison long-term memory because it doesn't exist, but the promised feature of remembering customer preferences across sessions is entirely vaporware.

### 2. Conversation Checkpoints (Unbounded Cost & Context)
- **The Issue:** `chat_service.py` delegates conversation memory entirely to LangGraph's `PostgresSaver` via the `thread_id` (conversation ID). Every single turn, tool call, scratchpad thought, and PII string is appended to the checkpoint blob.
- **Prompt Injection & Cost:** Because there is no message pruning, windowing, or summarization implemented, LangGraph injects the *entire* historical message array into the Orchestrator prompt on every turn. In a long customer support thread, this will result in massive context windows, causing extreme token costs and severely degraded reasoning quality.

### 3. Data Deletion & Privacy (GDPR/CCPA Non-Compliance)
- **The Issue:** The system promises privacy, but a customer's data cannot be fully deleted on request. 
- **The Reality:** While `scheduler.py` has a hard-delete cron job, it *only* triggers if the parent **Workspace** or **User (Agent Operator)** deletes their account. There is no API route, worker task, or database script to delete an individual *Customer's* data from an active workspace.
- **Outcome:** Customer PII, order numbers, and chat histories are permanently stored in the Postgres `checkpoints` and `conversation_turns` tables, rendering the system non-compliant with standard data deletion requests.
