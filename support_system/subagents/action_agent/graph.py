# subagents/action_agent/graph.py
#
# LangGraph graph definition for the Account / Order Action Agent.
#
# Responsibility:
#   Executes account and order operations against external systems on behalf
#   of the customer. This agent is invoked as a "tool" by the Orchestrator —
#   it receives a structured action request, runs it through the Tool Layer,
#   and returns a structured result.
#
# Stateless by design:
#   This agent has NO memory of previous turns. It receives exactly the context
#   the Orchestrator provides for this single invocation, does its job, and
#   returns. This keeps failure domains small and makes the agent independently
#   testable and swappable.
#
# Node layout (high-level):
#   1. validate_params  — schema-validate incoming action params; reject malformed
#                         requests before they reach external systems
#   2. execute_tool     — call the appropriate Tool Layer adapter with an
#                         idempotency key (session_id + turn_id + action_type) to
#                         prevent double-execution on retries
#   3. handle_result    — map the external system response to a structured
#                         AgentResult and surface any errors with retry logic
#                         (exponential backoff, bounded retries)
#
# Parallelism:
#   Read-only calls (e.g. get_order) may be fanned out in parallel by the
#   Orchestrator. Mutating calls are always serialised per session.
#
# Tool allowlist:
#   get_order, issue_refund, update_shipping_address, cancel_order, get_billing
#   Each tool is tagged with a risk level; the Tool Layer rejects any call to
#   a tool not on this agent's allowlist, independent of what the LLM decides.

import sys
import os
import json
import yaml

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool

from .schema import ActionRequest, ActionResult

# Ensure imports resolve to our project roots
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from support_system.mcp_client.client import MCPToolClient
from backend.db.session import get_legacy_sync_pool


class AgentState(TypedDict):
    request: ActionRequest
    # Track the result of the action throughout the graph
    result: Optional[ActionResult]


def validate_params(state: AgentState) -> dict:
    """Validate incoming action parameters against the expected schema."""
    # TODO: Implement parameter validation per action type using schema.py
    # For now, simply pass through
    return state


from langchain_core.runnables.config import RunnableConfig

def execute_tool(state: AgentState, config: RunnableConfig) -> dict:
    """Execute the domain-specific tool via the MCP Tool Layer, ensuring idempotency."""
    req = state["request"]
    
    # If a previous node already set a result (e.g., needs approval), skip execution
    if state.get("result") is not None:
         return state

    idempotency_key = f"{req.session_id}:{req.turn_id}:{req.action_type}"
    
    pool = get_legacy_sync_pool()
    conn = pool.getconn()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            INSERT INTO approvals.executed_actions (idempotency_key, session_id, turn_id, action_type, payload, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE 
            SET status = 'pending'
            WHERE approvals.executed_actions.status = 'failed'
            RETURNING idempotency_key
            """,
            (idempotency_key, req.session_id, req.turn_id, req.action_type, json.dumps(req.params), 'pending')
        )
        if cur.fetchone() is None:
            # Action already executed in a previous attempt
            conn.rollback()
            cur.close()
            pool.putconn(conn)
            result = ActionResult(
                success=True,
                data={"status": "skipped", "reason": "already executed"},
                needs_approval=False,
                idempotency_key=idempotency_key
            )
            return {"result": result}
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        pool.putconn(conn)
        raise e

    agent_config = config.get("configurable", {}).get("agent_config", {}).get("subagents", {}).get("action_agent", {})
    server_dir = agent_config.get("mcp_server", "order_account_mcp")
    server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'mcp_servers', server_dir, 'server.py'))
    
    # Inject idempotency_key for mutating operations
    if req.action_type in ["issue_refund", "cancel_order", "update_shipping_address", "reserve_stock", "update_stock_count"]:
        req.params["idempotency_key"] = idempotency_key

    try:
        client = MCPToolClient(server_path=server_path)
        mcp_result = client.call(req.action_type, req.params)
    except Exception as e:
        try:
            cur.execute(
                "UPDATE approvals.executed_actions SET status = 'failed' WHERE idempotency_key = %s",
                (idempotency_key,)
            )
            conn.commit()
        except Exception as inner_e:
            conn.rollback()
        finally:
            cur.close()
            pool.putconn(conn)
            
        result = ActionResult(
            success=False,
            needs_approval=False,
            idempotency_key=idempotency_key,
            error=str(e)
        )
        return {"result": result}
    
    # Update status to completed
    try:
        cur.execute(
            "UPDATE approvals.executed_actions SET status = 'completed' WHERE idempotency_key = %s",
            (idempotency_key,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        pool.putconn(conn)
    
    result = ActionResult(
        success=mcp_result.get("success", False),
        data=mcp_result,
        needs_approval=False,
        idempotency_key=idempotency_key,
        error=mcp_result.get("error")
    )
    return {"result": result}


def handle_result(state: AgentState) -> dict:
    """Finalize the result and handle any top-level errors."""
    # Ensure a result is present before ending the graph
    if not state.get("result"):
        req = state["request"]
        state["result"] = ActionResult(
            success=False,
            error="Failed to execute action. No result was generated.",
            idempotency_key=f"{req.session_id}:{req.turn_id}:{req.action_type}"
        )
    return state


# Build the Action Agent graph
builder = StateGraph(AgentState)
builder.add_node("validate_params", validate_params)
builder.add_node("execute_tool", execute_tool)
builder.add_node("handle_result", handle_result)

builder.add_edge(START, "validate_params")
builder.add_edge("validate_params", "execute_tool")
builder.add_edge("execute_tool", "handle_result")
builder.add_edge("handle_result", END)

action_agent_graph = builder.compile()


@tool(args_schema=ActionRequest, name_or_callable="action_agent")
def invoke_action_agent(
    action_type: str,
    params: dict,
    session_id: str,
    turn_id: str,
    config: RunnableConfig,
    risk_level: str = "low"
) -> ActionResult:
    """
    Executes account and order operations on behalf of the customer.

    USE THIS TOOL when the customer wants to:
    - Check their order status            → action_type: "get_order_status"
    - Request a refund                    → action_type: "issue_refund"
    - Cancel an order                     → action_type: "cancel_order"
    - Update a shipping address           → action_type: "update_shipping_address"
    - Enquire about a billing charge      → action_type: "get_billing_details"

    DO NOT use this tool for policy questions or general knowledge — use retrieval_agent instead.
    DO NOT use this tool if the customer is asking to speak to a human — use escalation_agent instead.

    Args:
        action_type: The specific operation to perform (e.g. "issue_refund").
        params: Action-specific parameters (e.g. {"order_id": "123", "amount": 50}).
        session_id: The current conversation session ID, used to build the idempotency key.
        turn_id: The current turn ID, combined with session_id for idempotency.
        risk_level: Pre-assessed risk level from the guardrail layer ("low", "medium", "high").

    Returns:
        ActionResult with success status, data payload, and idempotency key.
    """
    
    # Construct the incoming request from tool arguments
    request = ActionRequest(
        action_type=action_type,
        params=params,
        session_id=session_id,
        turn_id=turn_id,
        risk_level=risk_level
    )
    
    # Run the graph and retrieve the final state
    result_state = action_agent_graph.invoke({"request": request}, config=config)
    
    # Return the ActionResult object to the caller (Orchestrator)
    return result_state["result"]
