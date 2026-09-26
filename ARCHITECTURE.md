# Architecture

The Autonomi Support System uses a multi-agent orchestrated pattern backed by a FastAPI HTTP server, a PostgreSQL database (with pgvector), and an ARQ task worker. 

## System Components
1. **API Server (FastAPI)**: Stateless HTTP server that handles authentication, workspace management, and incoming chat turns. No WebSockets are used; all chat interactions are HTTP POSTs.
2. **Background Worker (ARQ + Redis)**: Handles long-running or non-blocking tasks, specifically document processing and async LangGraph resumption after an operator approves a high-risk action.
3. **Database (PostgreSQL + pgvector)**: Acts as the unified storage layer. Stores application state, LangGraph checkpoints (for pausing/resuming graphs), and document embeddings for the Retrieval Agent.
4. **Agent Orchestrator (LangGraph)**: The core reasoning engine. A ReAct loop that routes between long-term memory retrieval, guardrail checks, and subagent tools.
5. **Next.js Frontend (External)**: An external repository that provides the admin UI.

## Data Flow: Standard Conversation Turn
```mermaid
sequenceDiagram
    participant C as Client (HTTP)
    participant API as FastAPI
    participant LG as LangGraph (root_agent)
    participant DB as Postgres (Checkpoints)
    participant Sub as Subagents

    C->>API: POST /api/v1/chat/... (message)
    API->>LG: invoke(thread_id, message)
    LG->>DB: load_memory
    LG->>LG: orchestrator_agent (LLM decides next action)
    LG->>LG: guardrail_check (Risk=LOW)
    LG->>Sub: execute_tools (e.g. retrieval_agent)
    Sub-->>LG: tool_results
    LG->>LG: orchestrator_agent (LLM synthesises reply)
    LG->>DB: save_memory
    LG-->>API: Final AIMessage
    API-->>C: 200 OK (Reply)
```

## Data Flow: High-Risk Action (HITL)
```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant LG as LangGraph (root_agent)
    participant ARQ as ARQ Worker
    
    C->>API: POST (Request high-risk action)
    API->>LG: invoke()
    LG->>LG: orchestrator_agent (Requests Action)
    LG->>LG: guardrail_check (Risk=HIGH)
    LG->>LG: Route to escalation_agent
    LG->>LG: interrupt() (Pauses Graph)
    LG-->>API: Graph Paused
    API-->>C: 200 OK (Status: Pending Approval)
    
    Note over C, ARQ: Operator reviews request in Frontend
    C->>API: POST /api/v1/approvals/.../approve
    API->>ARQ: Enqueue resume_agent_graph(decision)
    ARQ->>LG: Command(resume=decision)
    LG->>LG: execute_tools (Action executed)
    LG->>LG: synthesise (Final Reply)
```

## Key Architectural Decisions
- **HTTP vs WebSockets**: Chat is currently implemented via stateless HTTP POSTs, not WebSockets, to simplify initial scaling and infrastructure.
- **LangGraph Checkpoints in Postgres**: By writing LangGraph checkpoints directly to Postgres, agent executions can be safely paused (interrupt) and resumed by entirely different worker instances.
- **Guardrails Pre-empt Subagents**: The Orchestrator's requested tool calls are intercepted and vetted *before* being executed by the Action Agent, ensuring dangerous parameters are caught early.

## Known Limitations & Gaps
- **Single Postgres Instance / No True RLS Multi-tenancy**: While multi-tenancy is modeled via `workspace_id`, the API connects as a standard Postgres user; true Row-Level Security (RLS) enforcement at the connection layer is not currently implemented.
- **Hybrid Search**: Currently, retrieval relies purely on dense vector similarity search; BM25 or hybrid cross-encoder reranking is not implemented in the current iteration.

*Last verified against commit/code state: Checked support_system/root_agent/graph.py, backend/worker.py, and chat routers.*
