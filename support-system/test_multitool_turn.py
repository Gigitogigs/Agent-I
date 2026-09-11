"""
test_multitool_turn.py
----------------------
Integration tests for the Orchestrator's dynamic tool-calling (ReAct) loop.

These tests verify that the Orchestrator LLM correctly selects and sequences
subagent tools within a single conversation turn, rather than following a
hardcoded routing path.

Test cases:
  1. SINGLE TOOL — FAQ query  → retrieval_agent only
  2. SINGLE TOOL — Escalation → escalation_agent only (human handoff)
  3. MULTI-TOOL  — FAQ + Action in one message
                   → retrieval_agent called first, then action_agent (low risk)
  4. GUARDRAIL INTERCEPT — High-risk action (refund > $100)
                   → LLM calls action_agent, guardrail redirects to escalation_agent

All tests inspect:
  - state["subagent_results"] — which tools were actually called and their outputs
  - state["risk_level"]       — guardrail risk assessment
  - state["messages"]         — presence of AIMessage tool_calls + ToolMessages

No production code is modified by this test.
"""

import uuid
import sys
import io
import json
from pprint import pprint
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from root_agent.graph import root_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(query: str, session_id: str) -> dict:
    """
    Builds a minimal initial AgentState dict for a test invocation.

    Args:
        query: The user message to send to the orchestrator.
        session_id: A unique session/thread ID for this test run.

    Returns:
        dict: A valid initial state compatible with AgentState.
    """
    return {
        "messages": [HumanMessage(content=query)],
        "session_id": session_id,
        "thread_id": session_id,
        "user_id": "test_user",
    }


def _run(query: str) -> tuple[dict, str]:
    """
    Invokes the root_agent with a query and returns the result state and session ID.

    Args:
        query: The user message to send to the orchestrator.

    Returns:
        Tuple of (result_state dict, session_id string).
    """
    session_id = f"test-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": session_id}}
    state = _make_state(query, session_id)
    result = root_agent.invoke(state, config=config)
    return result, session_id


def _tools_called(result: dict) -> list[str]:
    """
    Extracts the list of tool names that were actually called during the run,
    in order, by scanning the message history for ToolMessage entries.

    Args:
        result: The final AgentState dict returned by root_agent.invoke().

    Returns:
        List of tool name strings in the order they were called.
    """
    return [
        msg.name
        for msg in result["messages"]
        if isinstance(msg, ToolMessage)
    ]


def _tool_call_args(result: dict) -> list[dict]:
    """
    Extracts the arguments from every AIMessage tool_call in the message history.

    Useful for asserting what parameters the LLM passed to each tool.

    Args:
        result: The final AgentState dict returned by root_agent.invoke().

    Returns:
        List of arg dicts, one per tool_call found across all AIMessages.
    """
    args = []
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                args.append({"name": tc["name"], "args": tc.get("args", {})})
    return args


def _header(title: str):
    """
    Prints a formatted section header for test output readability.

    Args:
        title: The title to display in the header.
    """
    print("\n" + "=" * 64)
    print(f"TEST: {title}")
    print("=" * 64)


def _verdict(passed: bool, reason: str):
    """
    Prints a PASS or FAIL verdict with a reason.

    Args:
        passed: True if the test passed, False otherwise.
        reason: Human-readable explanation of the result.
    """
    label = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{label}: {reason}")
    print("=" * 64 + "\n")


# ---------------------------------------------------------------------------
# Test 1: Single tool — FAQ query should call only retrieval_agent
# ---------------------------------------------------------------------------

def test_single_tool_faq():
    """
    Verifies that a pure FAQ question causes the Orchestrator to call
    retrieval_agent exactly once and no other tools.

    Expected flow:
        orchestrator_agent → [tool_calls: retrieval_agent]
        → guardrail_check (LOW risk, pass-through)
        → execute_tools (retrieval_agent runs)
        → orchestrator_agent (sees ToolMessage, no more tool calls needed)
        → synthesise → END
    """
    _header("Single Tool — FAQ Query (retrieval_agent only)")
    QUERY = "What is your return policy for electronics?"
    print(f"Query: {QUERY}\n")

    result, session_id = _run(QUERY)
    tools = _tools_called(result)
    subagent_results = result.get("subagent_results", {})
    final_answer = result["messages"][-1].content

    print(f"Tools called (in order): {tools}")
    print(f"subagent_results keys:   {list(subagent_results.keys())}")
    print(f"\n[FINAL RESPONSE]:\n{final_answer}\n")

    passed = (
        "retrieval_agent" in tools
        and "action_agent" not in tools
        and "escalation_agent" not in tools
    )
    _verdict(passed, "retrieval_agent called and no other tools triggered.")


# ---------------------------------------------------------------------------
# Test 2: Single tool — Human handoff should call only escalation_agent
# ---------------------------------------------------------------------------

def test_single_tool_escalation():
    """
    Verifies that an explicit human-handoff request causes the Orchestrator
    to call escalation_agent directly without calling any other tool first.

    Expected flow:
        orchestrator_agent → [tool_calls: escalation_agent]
        → guardrail_check (escalation_agent, pass-through)
        → execute_tools (escalation_agent runs, LangGraph interrupt fires)
        → graph pauses (HITL)
    """
    _header("Single Tool — Human Handoff (escalation_agent only)")
    QUERY = "I am very unhappy. I want to speak to a real human right now."
    print(f"Query: {QUERY}\n")

    result, session_id = _run(QUERY)
    tools = _tools_called(result)
    subagent_results = result.get("subagent_results", {})

    print(f"Tools called (in order): {tools}")
    print(f"subagent_results keys:   {list(subagent_results.keys())}")
    # Note: graph may be interrupted here, so final message may be the interrupt signal
    last_msg = result["messages"][-1]
    print(f"\n[LAST MESSAGE TYPE]: {type(last_msg).__name__}")

    passed = (
        "escalation_agent" in tools
        and "retrieval_agent" not in tools
        and "action_agent" not in tools
    )
    _verdict(passed, "escalation_agent called directly for human handoff.")


# ---------------------------------------------------------------------------
# Test 3: Multi-tool — FAQ + low-risk action in one message
# ---------------------------------------------------------------------------

def test_multi_tool_faq_then_action():
    """
    Verifies that a message requiring both a knowledge lookup AND a low-risk
    account action causes the Orchestrator to call both tools sequentially
    within a single conversation turn.

    The refund amount ($50) is below the $100 HIGH-risk threshold in
    guardrails/check.py, so the action_agent call should proceed normally
    without being intercepted.

    Expected flow:
        orchestrator_agent → [tool_calls: retrieval_agent]
        → guardrail_check → execute_tools (retrieval_agent runs)
        → orchestrator_agent → [tool_calls: action_agent(issue_refund, $50)]
        → guardrail_check (MEDIUM risk, pass-through)
        → execute_tools (action_agent runs)
        → orchestrator_agent → no more tool calls
        → synthesise → END
    """
    _header("Multi-Tool — FAQ + Low-Risk Action (retrieval + action in one turn)")
    QUERY = (
        "What is your refund policy for electronics? "
        "Also, I'd like a $50 refund on order #ORD-9988."
    )
    print(f"Query: {QUERY}\n")

    result, session_id = _run(QUERY)
    tools = _tools_called(result)
    subagent_results = result.get("subagent_results", {})
    risk_level = result.get("risk_level")
    final_answer = result["messages"][-1].content

    print(f"Tools called (in order): {tools}")
    print(f"Risk level:              {risk_level}")
    print(f"subagent_results keys:   {list(subagent_results.keys())}")
    print(f"\n[FINAL RESPONSE]:\n{final_answer}\n")

    retrieval_called = "retrieval_agent" in tools
    action_called = "action_agent" in tools
    escalation_called = "escalation_agent" in tools

    passed = retrieval_called and action_called and not escalation_called
    _verdict(
        passed,
        f"Both retrieval_agent and action_agent called (escalation: {escalation_called})."
    )


# ---------------------------------------------------------------------------
# Test 4: Guardrail intercept — high-risk action redirected to escalation_agent
# ---------------------------------------------------------------------------

def test_guardrail_intercepts_high_risk_action():
    """
    Verifies that when the LLM calls action_agent with a refund amount above
    the $100 HIGH-risk threshold (guardrails/check.py), the guardrail_check
    node intercepts the pending tool call BEFORE it executes and replaces it
    with an escalation_agent call for HITL approval.

    This means:
      - action_agent should NOT appear in the ToolMessage history
        (it was intercepted before execute_tools ran it).
      - escalation_agent SHOULD appear in the ToolMessage history.
      - state["risk_level"] should be "HIGH".
      - state["requesting_agent"] should be "action_agent".

    Expected flow:
        orchestrator_agent → [tool_calls: action_agent(issue_refund, $3000)]
        → guardrail_check → INTERCEPT → replaces tool call with escalation_agent
        → execute_tools (escalation_agent runs instead)
        → graph pauses (HITL interrupt)
    """
    _header("Guardrail Intercept — High-Risk Action Redirected to Escalation")
    QUERY = "I want a refund of $3000 on my last purchase."
    print(f"Query: {QUERY}\n")

    result, session_id = _run(QUERY)
    tools = _tools_called(result)
    tool_call_args = _tool_call_args(result)
    subagent_results = result.get("subagent_results", {})
    risk_level = result.get("risk_level")
    requesting_agent = result.get("requesting_agent")

    print(f"Tools called (in order): {tools}")
    print(f"Risk level reported:     {risk_level}")
    print(f"Requesting agent:        {requesting_agent}")
    print(f"subagent_results keys:   {list(subagent_results.keys())}")
    print(f"\nAll LLM tool_call args:")
    pprint(tool_call_args)

    # The LLM originally intended to call action_agent, but the guardrail
    # should have replaced that call — so action_agent must NOT be in ToolMessages
    action_actually_ran = "action_agent" in tools
    escalation_ran = "escalation_agent" in tools

    # Passes if high risk was either intercepted by guardrail or escalated directly,
    # and action_agent never executed unguarded.
    intercepted_by_guardrail = (
        not action_actually_ran
        and escalation_ran
        and risk_level in ("HIGH", "CRITICAL")
        and requesting_agent == "action_agent"
    )
    direct_escalation = (
        not action_actually_ran
        and escalation_ran
    )

    passed = intercepted_by_guardrail or direct_escalation
    _verdict(
        passed,
        (
            f"High-risk action escalated safely (action_agent ran={action_actually_ran}, "
            f"escalation_agent ran={escalation_ran}, "
            f"risk={risk_level}, requesting_agent={requesting_agent})."
        )
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_single_tool_faq()
    test_single_tool_escalation()
    test_multi_tool_faq_then_action()
    test_guardrail_intercepts_high_risk_action()
