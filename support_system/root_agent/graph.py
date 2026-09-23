# root_agent/graph.py
#
# LangGraph graph definition for the Orchestrator (root) Agent.
#
# Responsibility:
#   Assembles the full LangGraph StateGraph that drives a customer support
#   conversation from start to finish. This is the top-level execution
#   entry point — the FastAPI gateway invokes this graph per incoming turn.
#
# Architecture (ReAct tool-calling loop):
#   1. load_memory        — load session memory + long-term customer context
#   2. orchestrator_agent — the LLM with bound tools decides what to do next:
#                           it either calls a subagent tool or produces a final reply
#   3. guardrail_check    — if the LLM requested a tool call, inspect the call's
#                           arguments for risk; HIGH-risk calls are intercepted and
#                           rerouted to escalation_agent for HITL approval
#   4. execute_tools      — run the (possibly modified) tool call via ToolNode;
#                           results are appended as ToolMessages and merged into
#                           subagent_results for frontend consumption
#   ↺ loop back to orchestrator_agent — the LLM sees the ToolMessage result and
#                           decides whether to call another tool or reply directly
#   5. synthesise         — reached when no more tool calls are needed;
#                           combines all ToolMessage results into a final customer reply
#
# HITL interrupt:
#   If guardrail_check flags a HIGH-risk tool call, the escalation_agent is
#   invoked instead. The escalation_agent calls LangGraph's interrupt(), which
#   fully pauses execution and saves state to Postgres. The graph resumes when
#   an operator decision arrives via the approval endpoint.
#
# Checkpointer:
#   Wired in at compile time via PostgresSaver from memory/checkpointer.py.
#   Every node boundary is a potential resume point.

from typing import Literal, Optional

from support_system.harness.model_factory import build_model, load_config
from .state import AgentState
from .tools.tool_registry import resolve_tools
from .guardrails.check import validate_action
from support_system.guardrails.handrolled.risk_policy import get_expiration
from .prompts.prompts import ORCHESTRATOR_SYSTEM_PROMPT, SYNTHESISE_SYSTEM_PROMPT

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres import PostgresSaver
from support_system.memory.checkpointer import get_checkpointer
from support_system.memory.store import get_store
from langgraph.store.base import BaseStore
from langchain_core.runnables.config import RunnableConfig

from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, ToolMessage
from support_system.subagents.escalation_agent.schema import EscalationRequest
from support_system.subagents.action_agent.graph import invoke_action_agent
from support_system.subagents.retrieval_agent.graph import invoke_retrieval_agent
from support_system.subagents.escalation_agent.graph import invoke_escalation_agent

from .tools.tool_registry import resolve_tools, ALL_TOOLS


# ---------------------------------------------------------------------------
# Node: load_memory
# ---------------------------------------------------------------------------

def load_memory(state: AgentState, config: RunnableConfig, store: BaseStore) -> dict:
    """
    Loads long-term customer context into AgentState before intent processing.

    Retrieves any previously stored customer facts (preferences, history) from
    the persistent PostgresStore using the user_id as the lookup key.

    Args:
        state: The current AgentState for this conversation thread.
        config: LangGraph RunnableConfig carrying thread/session metadata.
        store: The LangGraph BaseStore (backed by Postgres) for long-term memory.

    Returns:
        dict: State update containing 'customer_context'.
    """
    user_id = state.get("user_id")
    namespace = ("customer_facts",)
    item = store.get(namespace, user_id) if user_id else None
    customer_context = item.value if item else {}
    return {"customer_context": customer_context}


# ---------------------------------------------------------------------------
# Node: orchestrator_agent
# ---------------------------------------------------------------------------

def orchestrator_agent(state: AgentState, config: RunnableConfig) -> dict:
    """
    The core reasoning node of the Orchestrator.

    Invokes the LLM with all registered subagent tools bound to it. The LLM
    receives the full conversation history plus a system prompt describing the
    tool-use policy. It either:
      - Returns an AIMessage with tool_calls (→ graph routes to guardrail_check)
      - Returns a plain AIMessage with no tool_calls (→ graph routes to synthesise)

    Args:
        state: The current AgentState containing messages and customer_context.
        config: RunnableConfig containing dynamic agent_config.

    Returns:
        dict: State update containing the new AIMessage appended to 'messages'.
    """
    agent_config = config.get("configurable", {}).get("agent_config", {}).get("orchestrator", {})
    llm = build_model(agent_config)
    tools = resolve_tools(agent_config.get("tools", []))
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    system_prompt_template = agent_config.get("system_prompt") or ORCHESTRATOR_SYSTEM_PROMPT
    system_prompt = system_prompt_template.format(
        customer_context=state.get("customer_context", {})
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Node: guardrail_check
# ---------------------------------------------------------------------------

def guardrail_check(state: AgentState) -> dict:
    """
    Inspects the LLM's pending tool call for risk before execution.

    Reads the tool_calls from the last AIMessage in the conversation. If the
    intended tool is the action_agent, the call's params are passed through
    validate_action() to determine risk level. For HIGH or CRITICAL risk, the
    tool call is overridden — the last AIMessage is replaced with one that
    calls escalation_agent instead, and the state is updated to record the
    risk level and the original requesting agent.

    For retrieval_agent and escalation_agent calls, or LOW/MEDIUM action_agent
    calls, the state is passed through unchanged.

    Args:
        state: The current AgentState. The last message must be an AIMessage
               with at least one tool_call.

    Returns:
        dict: State update. May modify 'messages', 'risk_level', and
              'requesting_agent' if a high-risk intercept occurs.
    """
    last_message = state["messages"][-1]

    # Safety check — should always be an AIMessage with tool_calls here
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    tool_call = last_message.tool_calls[0]
    tool_name = tool_call["name"]
    tool_args = tool_call.get("args", {})

    # Only action_agent calls need risk evaluation
    if tool_name != "action_agent":
        return {}

    risk = validate_action(tool_args.get("params", {}))

    if risk in ("HIGH", "CRITICAL"):
        # Build an escalation request from the guardrail intercept
        expires_at = get_expiration(risk)
        escalation_args = {
            "request": EscalationRequest(
                session_id=state.get("session_id", "unknown"),
                agent_id="action_agent",
                action_type="hitl_approval",
                payload=tool_args,
                risk_level=risk.lower(),
                expires_at=expires_at,
            ).model_dump()
        }

        # Replace the pending tool call with an escalation_agent call
        override_message = AIMessage(
            content="",
            tool_calls=[{
                "id": tool_call["id"],
                "name": "escalation_agent",
                "args": escalation_args,
            }]
        )

        return {
            "messages": [override_message],
            "risk_level": risk,
            "requesting_agent": "action_agent",
        }

    return {"risk_level": risk}


# ---------------------------------------------------------------------------
# Node: execute_tools (ToolNode wrapper that also populates subagent_results)
# ---------------------------------------------------------------------------

def build_execute_tools_node(tool_list: list):
    """
    Factory that creates an execute_tools node wrapping LangGraph's ToolNode.

    After the underlying ToolNode executes the tool, this wrapper extracts
    the result from each ToolMessage and merges it into 'subagent_results'
    keyed by tool name, so the frontend can consume structured results
    independently of the raw message stream.

    Args:
        tool_list: List of registered tool callables to expose to ToolNode.

    Returns:
        Callable: A node function compatible with StateGraph.add_node().
    """
    base_node = ToolNode(tool_list)

    def execute_and_record(state: AgentState) -> dict:
        """
        Executes the pending tool call and records results into subagent_results.

        Args:
            state: The current AgentState. The last message must be an AIMessage
                   with tool_calls populated.

        Returns:
            dict: State update with new ToolMessages in 'messages' and updated
                  'subagent_results' for frontend access.
        """
        result = base_node.invoke(state)
        new_subagent_results = dict(state.get("subagent_results") or {})

        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                new_subagent_results[msg.name] = msg.content

        return {**result, "subagent_results": new_subagent_results}

    return execute_and_record


# ---------------------------------------------------------------------------
# Node: synthesise
# ---------------------------------------------------------------------------

def synthesise(state: AgentState, config: RunnableConfig) -> dict:
    """
    Synthesises a final customer-facing reply from all accumulated tool results.

    Invoked when the Orchestrator LLM decides no further tool calls are needed.
    Passes the full conversation history (including all ToolMessages) plus the
    synthesise system prompt to the LLM to produce a coherent, professional reply.

    Args:
        state: The current AgentState containing the full message history.
        config: RunnableConfig containing dynamic agent_config.

    Returns:
        dict: State update appending the final AIMessage reply to 'messages'.
    """
    agent_config = config.get("configurable", {}).get("agent_config", {}).get("orchestrator", {})
    llm = build_model(agent_config)

    messages = state["messages"]
    prompt = f"{SYNTHESISE_SYSTEM_PROMPT}\n\nSubagent Results: {state.get('subagent_results', {})}"
    response = llm.invoke([SystemMessage(content=prompt)] + messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Edge routing functions
# ---------------------------------------------------------------------------

def should_call_tools(state: AgentState) -> Literal["guardrail_check", "synthesise"]:
    """
    Conditional edge: checks whether the last LLM message contains tool calls.

    Routes to 'guardrail_check' if the Orchestrator LLM wants to call a tool,
    or to 'synthesise' if it produced a direct reply.

    Args:
        state: The current AgentState. Inspects the last message.

    Returns:
        "guardrail_check" if tool_calls are present, otherwise "synthesise".
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "guardrail_check"
    return "synthesise"


# ---------------------------------------------------------------------------
# Build and compile the graph
# ---------------------------------------------------------------------------

builder = StateGraph(AgentState)

builder.add_node("load_memory", load_memory)
builder.add_node("orchestrator_agent", orchestrator_agent)
builder.add_node("guardrail_check", guardrail_check)
builder.add_node("execute_tools", build_execute_tools_node(ALL_TOOLS))
builder.add_node("synthesise", synthesise)

builder.add_edge(START, "load_memory")
builder.add_edge("load_memory", "orchestrator_agent")
builder.add_conditional_edges(
    "orchestrator_agent",
    should_call_tools,
    {
        "guardrail_check": "guardrail_check",
        "synthesise": "synthesise",
    }
)
builder.add_edge("guardrail_check", "execute_tools")
# Loop back: LLM evaluates the ToolMessage result and decides next action
builder.add_edge("execute_tools", "orchestrator_agent")
builder.add_edge("synthesise", END)

root_agent = builder.compile(
    checkpointer=get_checkpointer(),
    store=get_store()
)


def run_root():
    """
    Returns the compiled root_agent graph for use by the FastAPI gateway.

    Returns:
        The compiled LangGraph CompiledStateGraph instance.
    """
    return root_agent
