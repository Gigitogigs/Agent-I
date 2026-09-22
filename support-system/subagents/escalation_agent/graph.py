# subagents/escalation_agent/graph.py
#
# LangGraph graph definition for the Escalation / HITL Agent.
#
# Responsibility:
#   Manages two related but distinct flows:
#   1. HITL (Human-in-the-Loop) approval — when a guardrail flags a HIGH-risk
#      action, this agent creates an approval checkpoint, notifies an operator,
#      enforces the SLA timer, and applies the expiry policy if the operator
#      doesn't respond in time.
#   2. Human handoff — when a request is out-of-scope, the customer explicitly
#      asks to speak to a human, or a prior subagent exhausts all retries, this
#      agent packages the conversation context and routes it to a human support
#      agent queue.
#
# Stateless by design:
#   Like all subagents, this agent holds no cross-turn memory. The HITL state
#   (pending/approved/rejected/expired/cancelled) lives in Postgres, not here.
#
# Node layout (high-level):
#   1. create_checkpoint — write an approval record to the Postgres HITL table
#                          with status=pending, risk metadata, and expiry timestamp
#   2. notify_operator   — push a notification via Redis queue → Notification Worker
#                          (webhook primary, email fallback if webhook fails)
#   3. await_decision    — LangGraph interrupt() — graph fully pauses here;
#                          resumes when operator calls the approval HTTP endpoint
#                          which publishes a Redis pub/sub resume signal
#   4. apply_decision    — map operator decision (approved/rejected/expired) to
#                          the appropriate Orchestrator continuation:
#                            approved  → Orchestrator continues with the action
#                            rejected  → Orchestrator surfaces rejection to customer
#                            expired   → auto-escalate per per-breakpoint-type config
#
# Decision authority:
#   This agent can NOT itself approve or reject — that authority belongs to
#   human operators only. The agent solely manages state transitions and timers.

import langgraph
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from typing import TypedDict, Annotated, Optional
from langgraph.types import interrupt
from langchain_core.runnables.config import RunnableConfig
from tenacity import retry, wait_exponential, stop_after_attempt

import uuid
import redis
import json
import os
from datetime import datetime

from .schema import EscalationRequest, EscalationResults
from harness.model_factory import build_model, load_config
from memory.checkpointer import get_checkpointer
from dotenv import load_dotenv

load_dotenv(override=True)

llm_config = load_config()
escalation_config = llm_config.get("subagents", {}).get("escalation_agent", {})
llm = build_model(escalation_config)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL)

import sys
import os

# Ensure imports resolve to our project roots
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from approvals.app.db import get_conn, release_conn



class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    escalation_request: EscalationRequest
    escalation_results: EscalationResults
    hitl_checkpoint_id: Optional[str]
    operator_decision: Optional[str]

def create_checkpoint(state: AgentState, config: RunnableConfig):
    """
    Creates a new HITL checkpoint record in Postgres for approval.
    """
    request = state['escalation_request']
    langgraph_checkpoint_id = config["configurable"]["checkpoint_id"]
    
    expires_at = request.expires_at

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO approval_requests (
                conversation_id,
                workspace_id,
                agent_id, -- TODO: pass agent_id logic in orchestrator agent 
                action_type,
                payload,
                risk_level,
                status,
                expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                request.conversation_id,
                request.workspace_id,
                request.agent_id,
                request.action_type,
                json.dumps({
                    "action": request.payload,
                    "checkpoint_id": langgraph_checkpoint_id,
                }),
                request.risk_level,
                "pending",
                expires_at
            )
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("No ID returned from INSERT statement.")
        generated_id = row[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_conn(conn)
    
    results = EscalationResults(
        id = str(generated_id),
        conversation_id = request.conversation_id,
        reviewer_role = "",
        resolved_by = None,
        status = "pending"
    )
    return {"escalation_results": results, "hitl_checkpoint_id": langgraph_checkpoint_id}


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True
)
def push_to_redis_with_retry(queue_name: str, payload: bytes):
    redis_client.lpush(queue_name, payload)

def notify_operator(state: AgentState, config: RunnableConfig):
    """
    Push notification  to Redis queue to alert human operator to approve/reject.
    """
    hitl_checkpoint_id = state["hitl_checkpoint_id"]
    conversation_id = state["escalation_request"].conversation_id

    notification = {
        "type": "hitl_notification",
        "checkpoint_id": hitl_checkpoint_id,
        "conversation_id": conversation_id,
        "risk_level": state["escalation_request"].risk_level,
    }

    notification_json = json.dumps(notification).encode("utf-8")

    try:
        push_to_redis_with_retry("operator_notifications", notification_json)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to notify operator after retries. {e}")

    return {"messages": ["Waiting for human approval ..."]} #return state updates if any

def await_decision(state: AgentState):
    """
    Pause the graph entirely using langgraph's interrupt.
    """
     # Calling interrupt() immediately freezes execution and saves state to Postgres.
    # The string passed in is optional metadata about WHY it paused.
    # When a human clicks "Approve" on your frontend and resumes the graph, 
    # whatever payload they send will be returned right here into the 'decision' variable.
    decision = interrupt(f"Awaiting human approval for checkpoint: {state['hitl_checkpoint_id']}")

    return {"operator_decision": decision}

def apply_decision(state: AgentState):
    """
    Apply the operator's decision to the graph state.
    """
    decision = state["operator_decision"]
    results = state["escalation_results"]

    # update the results based on what the human decided
    if isinstance(decision, dict):
        results.status = decision.get("status", "rejected")
    else:
        results.status = decision if decision else "rejected"

    results.resolved_at = datetime.now()
    status = results.status
    resolved_at = results.resolved_at

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE approval_requests
            SET resolved_at = %s, status = %s
            WHERE conversation_id = %s
            """,
            (
                resolved_at,
                status,
                state["escalation_request"].conversation_id
            )
        )
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_conn(conn)


    return {"escalation_results": results}

    #Build the graph
builder = StateGraph(AgentState)
builder.add_node("create_checkpoint", create_checkpoint)
builder.add_node("notify_operator", notify_operator)
builder.add_node("await_decision", await_decision)
builder.add_node("apply_decision", apply_decision)

builder.add_edge(START, "create_checkpoint")
builder.add_edge("create_checkpoint", "notify_operator")
builder.add_edge("notify_operator", "await_decision")
builder.add_edge("await_decision", "apply_decision")
builder.add_edge("apply_decision", END)

escalation_agent = builder.compile(checkpointer=get_checkpointer())

@tool(name_or_callable="escalation_agent")
def invoke_escalation_agent(request: EscalationRequest) -> EscalationResults:
    """
    Escalates a conversation to a human operator, or pauses for human approval before executing a high-risk action.

    WHEN TO USE THIS TOOL:
    - The customer says anything like: "I want to speak to a human", "let me talk to a real person",
      "connect me to a manager", "I want to make a complaint", or "I'm not satisfied with this answer".
    - The guardrail layer has flagged the proposed action as HIGH or CRITICAL risk.
    - The customer's request requires access, permissions, or authority that the automated system does not have.
    - All automated retry attempts have been exhausted without resolving the issue.

    WHEN NOT TO USE THIS TOOL:
    - The question can be answered using the knowledge base — use the retrieval_agent instead.
    - The action is a standard, low-risk operation (e.g. checking order status, looking up a policy).
    - The customer is simply frustrated — attempt to resolve their issue first before escalating.

    INPUTS: Provide a fully populated EscalationRequest including the session_id, escalation_type
    ("hitl_approval" for risk approvals, "human_handoff" for direct human routing), the proposed
    action dict, risk_level, risk_reason, and the sla_seconds deadline for operator response.

    OUTPUTS: Returns an EscalationResults object containing the operator's final status
    ("approved", "rejected", or "expired"), an optional operator_note explaining their decision,
    and the resolved_at timestamp. Use the status to decide how to continue the conversation.
    """
    initial_state = {
        "escalation_request": request,
        "messages": []
    }
    
    # We must pass a thread_id in the config so the checkpointer can save the interrupt state.
    # Using checkpoint_ns isolates this subagent's memory from the orchestrator's memory.
    config = {"configurable": {"thread_id": request.conversation_id, "checkpoint_ns": "escalation_agent"}}
    
    result_state = escalation_agent.invoke(initial_state, config=config)
    
    return result_state["escalation_results"]
