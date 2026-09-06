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
from .tools.tool_registry import resolve_tools
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

root_config = load_config()["orchestrator"]
llm = build_model(root_config)
llm_with_tools = resolve_tools(root_config["tools"])

def get_tool(name: str):
    """Look up a tool from llm_with_tools by its registered name."""
    for t in llm_with_tools:
        if t.name == name:
            return t
    raise KeyError(f"Tool '{name}' not found in the tool registry.")


def load_memory(state: AgentState, config: RunnableConfig, store: BaseStore):
    """
    Loads session and long-term customer context into the AgentState. this happens before intent classification
    """
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    thread_id = state.get("thread_id")
    
    #fetch long-term context from the store using a "customer_facts" namespace
    namespace = ("customer_facts",)
    item = store.get(namespace, user_id)
    
    customer_context = item.value if item else {}
    
    return {"customer_context": customer_context}

def classify_intent(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1].content
    decision = get_router_decision(llm, last_message)
    return {
        "intent": decision.intent,
        "urgency": decision.urgency,
        "requires_human": decision.requires_human
    }

def route_to_subagent(state: AgentState):
    intent = state.get("intent")
    if state.get("requires_human") or intent == "escalation":
        return "run_escalation_agent"
    if intent == "order_action":
        return "run_action_agent"
    return "run_retrieval_agent"

def run_retrieval_agent(state: AgentState):
    prior_messages = state["messages"][:-1]
    context_slice = [
        f"{msg.type}: {msg.content}"
        for msg in prior_messages[-4:]
    ]

    retrieval_agent = get_tool("retrieval_agent")
    result = retrieval_agent.invoke({
        "query": state["messages"][-1].content,
        "context_slice": context_slice,
        "filters": state.get("customer_context", {}).get("preferences")
    })
    return {"subagent_results": {"retrieval": {"answer": result.answer, "source_chunks": result.source_chunks}}}

def run_action_agent(state: AgentState):
    # TODO: Wire up action_agent tool once implemented
    result = {"action": "mock_refund", "refund_amount": 150}
    return {"subagent_results": {"action": result}}

def run_escalation_agent(state: AgentState):
    escalation_tool = get_tool("escalation_agent")
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

    result = escalation_tool.invoke({"request": request})
    return {"subagent_results": {"escalation": {"status": result.status, "id": result.id}}}

def guardrail_check(state: AgentState):
    results = state.get("subagent_results", {})
    action_payload = results.get("action", {})
    risk = validate_action(action_payload)

    requesting_agent = None
    if results:
        first_key = next(iter(results.keys()))
        requesting_agent = f"{first_key}_agent"

    return {"risk_level": risk, "requesting_agent": requesting_agent}

def route_after_guardrail(state: AgentState):
    if state.get("risk_level") in ("HIGH", "CRITICAL"):
        return "run_escalation_agent"
    return "synthesise"

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
        "run_action_agent": "run_action_agent",
        "run_escalation_agent": "run_escalation_agent"
    }
)
builder.add_edge("run_retrieval_agent", "guardrail_check")
builder.add_edge("run_action_agent", "guardrail_check")
builder.add_edge("run_escalation_agent", "synthesise")

builder.add_conditional_edges(
    "guardrail_check",
    route_after_guardrail,
    {
        "run_escalation_agent": "run_escalation_agent",
        "synthesise": "synthesise"
    }
)
builder.add_edge("synthesise", END)

# Compile using checkpointer and store
root_agent = builder.compile(
    checkpointer=get_checkpointer(),
    store=get_store()
)

def run_root():
    return root_agent
