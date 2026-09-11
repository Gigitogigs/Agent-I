# approvals/app/main.py
#
# FastAPI application for the HITL Approval backend.
#
# Responsibility:
#   Exposes HTTP endpoints that the operator frontend (TBD: Next.js / React)
#   calls to list pending approvals, inspect individual approval details, and
#   submit an approve / reject / cancel decision.
#
# On decision submission:
#   1. The DB record in approvals.approval_requests is updated atomically.
#   2. The paused LangGraph execution is resumed by calling
#      escalation_agent.invoke(Command(resume=decision), ...) — the interrupt()
#      inside await_decision receives the decision payload and the graph
#      continues through apply_decision → END.
#
# ---- Architecture note on resume target ----------------------------------------
#   The escalation_agent is compiled as a separate LangGraph graph (its own
#   checkpointer, thread_id = session_id). The interrupt() fires inside THAT
#   graph, not inside the root orchestrator.  We therefore resume the
#   escalation_agent directly.
#
#   If in future the escalation agent is refactored into the root orchestrator
#   as an inline subgraph, the resume target changes to root_agent. The
#   endpoint logic below is designed so that only the import and the resume
#   call need to change — no structural API changes required.
# ---------------------------------------------------------------------------------
#
# Endpoints:
#   GET  /api/approvals/pending            — dashboard list of all pending items
#   GET  /api/approvals/{approval_id}      — full detail for one approval
#   POST /api/approvals/{approval_id}/decide — operator submits a decision

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure the support-system root is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from .db import close_pool, get_conn, init_pool, release_conn
from .schemas import (
    ApprovalDecisionRequest,
    ApprovalDetailResponse,
    ApprovalListItem,
    DecisionResponse,
)

load_dotenv()


# ---------------------------------------------------------------------------
# Lifespan — pool lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="HITL Approval API",
    description="Backend API for the Human-In-The-Loop operator approval dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the frontend (TBD) to call this API from the browser.
# In production, replace "*" with the actual frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend origin in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /api/approvals/pending
# ---------------------------------------------------------------------------

@app.get("/api/approvals/pending", response_model=List[ApprovalListItem])
def list_pending_approvals():
    """
    Return all approval requests currently in 'pending' status, ordered by
    creation time (oldest first — highest SLA urgency at the top).

    The operator dashboard polls this endpoint to populate the queue.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, session_id, agent_id, action_type, risk_level,
                   status, created_at, expires_at
            FROM   approvals.approval_requests
            WHERE  status = 'pending'
            ORDER  BY created_at ASC
            """
        )
        rows = cur.fetchall()
        return [
            ApprovalListItem(
                id=str(row[0]),
                session_id=row[1],
                agent_id=row[2],
                action_type=row[3],
                risk_level=row[4],
                status=row[5],
                created_at=row[6],
                expires_at=row[7],
            )
            for row in rows
        ]
    finally:
        cur.close()
        release_conn(conn)


# ---------------------------------------------------------------------------
# GET /api/approvals/{approval_id}
# ---------------------------------------------------------------------------

@app.get("/api/approvals/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval_detail(approval_id: str):
    """
    Return the full detail for a single approval request, including the
    serialised action payload and assigned reviewer role.

    Called by the operator UI when they click into a specific approval to
    read the full context before deciding.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, session_id, agent_id, action_type, risk_level,
                   status, created_at, expires_at, payload, reviewer_role
            FROM   approvals.approval_requests
            WHERE  id = %s
            """,
            (approval_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Approval not found.")

        payload = row[8] if isinstance(row[8], dict) else json.loads(row[8])

        return ApprovalDetailResponse(
            id=str(row[0]),
            session_id=row[1],
            agent_id=row[2],
            action_type=row[3],
            risk_level=row[4],
            status=row[5],
            created_at=row[6],
            expires_at=row[7],
            payload=payload,
            reviewer_role=row[9],
        )
    finally:
        cur.close()
        release_conn(conn)


# ---------------------------------------------------------------------------
# POST /api/approvals/{approval_id}/decide
# ---------------------------------------------------------------------------

@app.post("/api/approvals/{approval_id}/decide", response_model=DecisionResponse)
def decide_approval(approval_id: str, body: ApprovalDecisionRequest):
    """
    Submit an operator decision (approved / rejected / cancelled) for a
    pending approval request.

    Steps:
      1. Validate the approval exists and is still 'pending'
         (409 if already resolved — prevents double-clicks / double-approvals).
      2. Update the DB record atomically (status, resolved_at, resolved_by).
      3. Resume the paused LangGraph escalation_agent so it can apply the
         decision and unblock the conversation.

    If step 3 fails (e.g. the process running the graph restarted), the DB
    is already updated correctly and a 'warning' field is returned so the
    caller knows to trigger a manual resume or check the graph state.
    """
    conn = get_conn()
    session_id: str | None = None

    # ------------------------------------------------------------------
    # Step 1 & 2: Validate + update DB
    # ------------------------------------------------------------------
    try:
        cur = conn.cursor()

        # Fetch current state
        cur.execute(
            "SELECT session_id, status FROM approvals.approval_requests WHERE id = %s",
            (approval_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Approval not found.")

        session_id, current_status = row[0], row[1]
        if current_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot decide: approval is already '{current_status}'.",
            )

        # Persist the decision
        cur.execute(
            """
            UPDATE approvals.approval_requests
            SET    status      = %s,
                   resolved_at = %s,
                   resolved_by = %s
            WHERE  id = %s
            """,
            (
                body.status,
                datetime.now(timezone.utc),
                body.resolved_by,
                approval_id,
            ),
        )
        conn.commit()

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        cur.close()
        release_conn(conn)

    # ------------------------------------------------------------------
    # Step 3: Resume the paused LangGraph graph
    # ------------------------------------------------------------------
    # The escalation_agent is compiled as a separate graph with its own
    # checkpointer. The interrupt() in await_decision is saved under
    # thread_id = session_id. We resume it by passing Command(resume=...)
    # with the same thread_id.
    #
    # Once resumed, apply_decision runs, updates the DB record again
    # (resolved_at, status on EscalationResults), and the graph ends —
    # which unblocks the root orchestrator's run_escalation_agent node.
    #
    # TODO: When the root orchestrator and escalation agent are refactored
    # to share a single compiled graph, change this import target to
    # `from root_agent.graph import root_agent` and resume that instead.
    try:
        from langgraph.types import Command
        from subagents.escalation_agent.graph import escalation_agent

        decision_payload = {
            "status": body.status,
            "operator_note": body.operator_note,
            "resolved_by": body.resolved_by,
        }

        escalation_agent.invoke(
            Command(resume=decision_payload),
            config={"configurable": {"thread_id": session_id}},
        )

    except Exception as exc:
        # DB is already committed — log and return a partial-success with a warning.
        # The graph can be manually resumed later using the same Command pattern.
        # TODO: emit a Langfuse incident span here when observability is wired up.
        print(
            f"[WARN] Approval DB updated but graph resume failed "
            f"for session '{session_id}': {exc}"
        )
        return DecisionResponse(
            status="recorded",
            decision=body.status,
            session_id=session_id,
            warning=f"Decision recorded in DB, but graph resume failed: {exc}",
        )

    return DecisionResponse(
        status="ok",
        decision=body.status,
        session_id=session_id,
    )
