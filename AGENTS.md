# Agent Architecture

The system uses a hierarchical, multi-agent pattern orchestrated via LangGraph. 
State is persisted to PostgreSQL, enabling agents to be paused and resumed across worker boundaries.

## 1. `root_agent` (The Orchestrator)
- **Purpose**: The primary entry point for all conversation turns. Manages context, routes to subagents (tools), and synthesizes final responses.
- **Input/Output**: Expects a `messages` array and outputs an updated `messages` array with the final reply.
- **Model**: Swappable via `agent_config` in the run config (defaults defined in `harness/model_factory.py`).
- **Tools**: It can call any registered subagent tool (`action_agent`, `retrieval_agent`, `escalation_agent`).
- **Surprising/Non-obvious behavior**:
  - The orchestrator has a hardcoded `guardrail_check` node that inspects pending tool calls *before* they execute. If the LLM requests an `action_agent` tool call with HIGH or CRITICAL risk, the guardrail intercepts it, overrides the LLM's requested tool call to `escalation_agent` instead, and forces a HITL approval flow.

## 2. `action_agent` (Order/Account Operations)
- **Purpose**: Executes mutating and read-only operations against external systems via the MCP layer.
- **Input/Output**: `ActionRequest` → `ActionResult`.
- **Tools**: Proxies calls to the external MCP server (e.g. `issue_refund`, `cancel_order`).
- **Failure/Edge cases**:
  - Mutating operations (e.g. refunds) require an `idempotency_key` constructed from `session_id + turn_id + action_type`. It writes this key to `approvals.executed_actions`. If a retry occurs, it will skip execution and return the previous result, preventing double-billing or double-actions.

## 3. `escalation_agent` (HITL & Handoff)
- **Purpose**: Pauses the system for human operator approval or fully hands off the conversation to a human.
- **Input/Output**: `EscalationRequest` → `EscalationResults`.
- **Surprising/Non-obvious behavior**:
  - This agent is entirely stateless across turns. It calls `interrupt()` to freeze the LangGraph state entirely. The state remains frozen in the Postgres checkpointer until an operator calls the `POST /api/v1/approvals/.../approve` endpoint, which signals the ARQ worker to unpause it using `Command(resume=...)`.
  - Also pushes a Redis notification for the operator.

## 4. `retrieval_agent` (Knowledge/FAQ)
- **Purpose**: Answers knowledge and policy questions strictly from the vector database. READ-ONLY.
- **Input/Output**: `RetrievalRequest` → `RetrievalResult`.
- **Surprising/Non-obvious behavior**:
  - Employs a HyDE (Hypothetical Document Embeddings) pattern via the `rewrite_query` node: it uses an LLM to generate a declarative statement, a hypothetical answer, and keywords *before* doing the vector search. 
  - Will explicitly return `"I don't have enough information in the knowledge base to answer this question."` if the retrieved chunks do not sufficiently cover the query, signaling the Orchestrator to escalate or ask for clarification.

*Last verified against commit/code state: Checked support_system/root_agent/graph.py, and support_system/subagents/[action, escalation, retrieval]/graph.py.*
