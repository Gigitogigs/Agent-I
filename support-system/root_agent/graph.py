# root_agent/graph.py
#
# LangGraph graph definition for the Orchestrator (root) Agent.
#
# Responsibility:
#   Assembles the full LangGraph StateGraph that drives a customer support
#   conversation from start to finish. This is the top-level execution
#   entry point — the FastAPI gateway invokes this graph per incoming turn.
#
# Node layout (high-level):
#   1. load_memory      — load session memory + long-term customer context
#   2. classify_intent  — call router.py to determine which subagent handles this turn
#   3. run_subagent     — fan out to retrieval_agent, action_agent, or
#                         escalation_agent depending on the routing decision;
#                         read-only subagents (RAG + order lookup) may run in
#                         parallel, mutating actions are always serialised
#   4. guardrail_check  — validate proposed action / model output before
#                         committing; may trigger an interrupt (HITL) if risk is HIGH
#   5. synthesise       — combine subagent results into a final reply for the customer
#   6. persist_memory   — write updated session memory and (end-of-conversation)
#                         long-term memory to Postgres
#   7. emit_trace       — fire Langfuse spans for this turn (async, fire-and-forget)
#
# HITL interrupt:
#   If guardrail_check flags a HIGH-risk action, the graph calls LangGraph's
#   interrupt() at that node. Execution fully pauses; the checkpointer saves
#   state to Postgres. The graph resumes when an operator decision arrives
#   via the approval endpoint (Redis pub/sub → graph.resume()).
#
# Checkpointer:
#   Wired in at graph compile time using the PostgresSaver from
#   memory/checkpointer.py. Every node boundary is a potential resume point.

from typing import Annotated, Literal

from harness.model_factory import build_model, load_config
from .state import AgentState
from .router import get_router_decision
from .guardrails.check import validate_action
from .prompts.prompts import SYNTHESISE_SYSTEM_PROMPT

from langgraph.types import interrupt
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import InMemorySaver
from memory.checkpointer import get_checkpointer
from memory.store import get_store
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from subagents.escalation_agent.schema import EscalationRequest
from subagents.action_agent.graph import invoke_action_agent
from subagents.retrieval_agent.graph import invoke_retrieval_agent
from subagents.escalation_agent.graph import invoke_escalation_agent

root_config = load_config()["orchestrator"]
llm = build_model(root_config)


def load_memory(state: AgentState, config: RunnableConfig, store: BaseStore):
    """
    Loads session and long-term customer context into the AgentState. this happens before intent classification
    """
    user_id = state.get("user_id")
    customer_context = {}
    
    if user_id:
        namespace = ("customer_facts",)
        item = store.get(namespace, user_id)
        if item:
            customer_context = item.value
            
    return {"customer_context": customer_context}

def classify_intent(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1].content
    decision = get_router_decision(llm, last_message)
    
    prior_messages = messages[:-1]
    context_slice = [
        f"{msg.type}: {msg.content}"
        for msg in prior_messages[-4:]
    ]
    
    return {
        "intents": decision.intents,
        "urgency": decision.urgency,
        "requires_human": decision.requires_human,
        "context_slice": context_slice
    }

def route_to_subagent(state: AgentState) -> list[str]:
    # NOTE: This plain-list routing is an intentional stepping stone. 
    # Target for Phase 5+ is a registry-driven Send fan-out architecture which will allow parameterized instances.
    intents = state.get("intents", [])
    if state.get("requires_human") or "escalation" in intents:
        return ["run_escalation_agent"]
        
    next_nodes = []
    if "order_action" in intents:
        next_nodes.append("guardrail_check")
    if "faq" in intents or not next_nodes:
        next_nodes.append("run_retrieval_agent")
        
    return list(set(next_nodes))

def run_retrieval_agent(state: AgentState):
    result = invoke_retrieval_agent.invoke({
        "query": state["messages"][-1].content,
        "context_slice": state.get("context_slice", []),
        "filters": state.get("customer_context", {}).get("preferences")
    })
    return {"subagent_results": {"retrieval": {"answer": result.answer, "source_chunks": result.source_chunks}}}

def run_action_agent(state: AgentState):
    # TODO: In a fully wired system, action_type and params should be extracted 
    # from the LLM's tool call request (state["messages"][-1].tool_calls).
    # For now, pass a placeholder based on intent to wire up the system
    action_type = "issue_refund"
    params = {"order_id": "12345", "amount": 150.0, "reason": "Customer request"}
    
    result = invoke_action_agent.invoke({
        "action_type": action_type,
        "params": params,
        "session_id": state["session_id"],
        "turn_id": f"turn_{len(state['messages'])}",
        "risk_level": state.get("risk_level", "low")
    })
    
    # action_tool returns an ActionResult. Dump it to a dict for the state
    action_data = result.model_dump() if hasattr(result, 'model_dump') else result
    return {"subagent_results": {"action": action_data}}

def run_escalation_agent(state: AgentState):
    last_message = state["messages"][-1].content

    # Pattern 2: Use the dynamic requesting_agent, fallback to orchestrator
    agent_id = state.get("requesting_agent") or "orchestrator"
    
    # If routed here from intent, it's handoff. If from guardrail, it's approval.
    action_type = "human_handoff" if agent_id == "orchestrator" else "hitl_approval"

    request = EscalationRequest(
        session_id=state["session_id"],
        agent_id=agent_id,
        action_type=action_type,
        payload={"query": last_message, "context": state.get("customer_context", {})},
        risk_level=state.get("risk_level", "HIGH").lower(),
    )

    result = invoke_escalation_agent.invoke({"request": request})
    return {"subagent_results": {"escalation": {"status": result.status, "id": result.id}}}

def guardrail_check(state: AgentState):
    # TODO: In a fully wired system, extract the action_payload from the LLM tool call in state
    # For now, we mock the payload that is about to be sent to the action agent
    action_payload = {"action_type": "issue_refund", "params": {"order_id": "12345", "amount": 150.0, "reason": "Customer request"}}
    risk = validate_action(action_payload)
    
    if risk in ("HIGH", "CRITICAL"):
        operator_decision = interrupt(f"Awaiting human approval for risk: {risk}")
        if isinstance(operator_decision, dict) and operator_decision.get("status") != "approved":
            return {
                "risk_level": risk, 
                "requesting_agent": "action_agent",
                "subagent_results": {"action": {"success": False, "error": "Human operator rejected the action."}}
            }

    return {"risk_level": risk, "requesting_agent": "action_agent"}

def route_after_guardrail(state: AgentState):
    results = state.get("subagent_results", {})
    if results and results.get("action", {}).get("success") is False:
        return "synthesise"
    return "run_action_agent"

def synthesise(state: AgentState):
    messages = state["messages"]
    results = state.get("subagent_results", {})
    prompt = f"{SYNTHESISE_SYSTEM_PROMPT}\n\nSubagent Results: {results}"
    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [response]}

# Build the Graph
builder = StateGraph(AgentState)
builder.add_node("load_memory", load_memory)
builder.add_node("classify_intent", classify_intent)
builder.add_node("run_retrieval_agent", run_retrieval_agent)
builder.add_node("run_action_agent", run_action_agent)
builder.add_node("run_escalation_agent", run_escalation_agent)
builder.add_node("guardrail_check", guardrail_check)
builder.add_node("synthesise", synthesise)

builder.add_edge(START, "load_memory")
builder.add_edge("load_memory", "classify_intent")
builder.add_conditional_edges(
    "classify_intent",
    route_to_subagent,
    {
        "run_retrieval_agent": "run_retrieval_agent",
        "guardrail_check": "guardrail_check",
        "run_escalation_agent": "run_escalation_agent"
    }
)
builder.add_edge("run_retrieval_agent", "synthesise")

builder.add_conditional_edges(
    "guardrail_check",
    route_after_guardrail,
    {
        "run_escalation_agent": "run_escalation_agent",
        "run_action_agent": "run_action_agent"
    }
)
builder.add_edge("run_action_agent", "synthesise")
builder.add_edge("run_escalation_agent", "synthesise")
builder.add_edge("synthesise", END)

# Compile using checkpointer and store
root_agent = builder.compile(
    checkpointer=get_checkpointer(),
    store=get_store()
)

def run_root():
    return root_agent
