"""
test_multitool_turn.py
----------------------
Tests whether the Orchestrator can call BOTH the retrieval_agent AND the
escalation_agent within a single conversation turn.

The expected flow for this capability is:
  classify_intent
        │  (intent = faq)
        ▼
  run_retrieval_agent   ── insufficient knowledge base coverage ──▶  run_escalation_agent
        │                                                                      │
        ▼ (sufficient coverage)                                                ▼
  guardrail_check ─────────────────────────────────────────────────────  synthesise

This test runs the unmodified codebase and checks whether the current
graph wiring actually implements this path. It will either:

  PASS  – both 'retrieval' and 'escalation' keys appear in subagent_results
          (the graph already supports this)

  FAIL (EXPECTED GAP)  – only 'retrieval' appears; the orchestrator routed
          to synthesise instead of escalating, meaning the fallback routing
          has not been implemented yet.

No production code is modified by this test.
"""

import uuid
import sys
import io
from pprint import pprint

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import HumanMessage
from root_agent.graph import root_agent


QUERY = "What is your refund policy for electronics?"


def test_multitool_fallback():
    session_id = f"test-multitool-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": session_id}}

    print("\n" + "=" * 64)
    print("TEST: Single-Turn Multi-Tool Fallback (Retrieval -> Escalation)")
    print(f"Session ID: {session_id}")
    print(f"Query: {QUERY}")
    print("=" * 64)
    print()

    initial_state = {
        "messages": [HumanMessage(content=QUERY)],
        "session_id": session_id,
        "thread_id": session_id,
        "user_id": "test_user_probe",
    }

    print("Invoking root agent...")
    result = root_agent.invoke(initial_state, config=config)

    subagent_results = result.get("subagent_results", {})
    risk_level = result.get("risk_level")
    requesting_agent = result.get("requesting_agent")
    final_answer = result["messages"][-1].content

    print("\n--- Raw Subagent Results ---")
    pprint(subagent_results)
    print(f"Risk Level reported: {risk_level}")
    print(f"Requesting Agent:    {requesting_agent}")
    print("---------------------------\n")

    # ── Step 1: Was retrieval_agent called? ──────────────────────────────────
    retrieval_called = "retrieval" in subagent_results
    retrieval_data   = subagent_results.get("retrieval", {})

    # The retrieval_agent's generate_answer node sets insufficient_coverage on
    # the RetrievalResult object. However, run_retrieval_agent in graph.py only
    # forwards 'answer' and 'source_chunks' — it drops insufficient_coverage.
    # We therefore detect insufficiency by inspecting the answer text itself.
    INSUFFICIENT_PHRASE = "I don't have enough information in the knowledge base"
    retrieval_answer     = retrieval_data.get("answer", "") or ""
    retrieval_missed     = INSUFFICIENT_PHRASE in retrieval_answer
    retrieval_source_ct  = len(retrieval_data.get("source_chunks", []))

    if retrieval_called:
        print(f"[STEP 1] retrieval_agent was called.  (source chunks: {retrieval_source_ct})")
        print(f"         Insufficient-coverage phrase detected in answer: {retrieval_missed}")
    else:
        print("[STEP 1] retrieval_agent was NOT called -- unexpected for an FAQ query.")

    # ── Step 2: Was escalation_agent subsequently called? ────────────────────
    escalation_called = "escalation" in subagent_results
    escalation_data   = subagent_results.get("escalation", {})

    if escalation_called:
        print(f"[STEP 2] escalation_agent was called.  Status: {escalation_data.get('status')}  "
              f"ID: {escalation_data.get('id')}")
    else:
        print("[STEP 2] escalation_agent was NOT called in this turn.")

    print(f"\n[FINAL RESPONSE]:\n{final_answer}\n")

    # ── Verdict ──────────────────────────────────────────────────────────────
    print("=" * 64)
    print("VERDICT")
    print("=" * 64)

    if retrieval_called and escalation_called:
        print("PASS: Orchestrator called BOTH tools in a single turn.")
        print("    retrieval_agent searched the KB, then escalation_agent was")
        print("    triggered in the same turn.")
    elif retrieval_called and retrieval_missed and not escalation_called:
        print("FAIL (EXPECTED GAP): Orchestrator called retrieval_agent")
        print("    and received an 'insufficient coverage' answer, but did NOT")
        print("    call escalation_agent afterwards.")
        print()
        print("    ROOT CAUSE: route_after_guardrail() in root_agent/graph.py")
        print("    only branches to run_escalation_agent when risk_level is HIGH")
        print("    or CRITICAL. For retrieval queries, validate_action() returns")
        print("    LOW (no action payload), so the graph routes to synthesise")
        print("    instead. The insufficient_coverage signal from the retrieval")
        print("    agent is also dropped by run_retrieval_agent (it forwards only")
        print("    'answer' and 'source_chunks', not 'insufficient_coverage').")
        print()
        print("    TO FIX: Add a conditional edge after guardrail_check that")
        print("    routes to run_escalation_agent when retrieval returned")
        print("    insufficient coverage, and forward that flag through state.")
    elif retrieval_called and not retrieval_missed:
        print("INCONCLUSIVE: retrieval_agent was called and returned a sufficient")
        print("    answer from the knowledge base. The fallback path was not triggered.")
        print("    Try a query the KB does not have an answer for, or verify your")
        print("    knowledge base does not contain electronics refund policy documents.")
    else:
        print("UNEXPECTED: Neither tool was called or an unexpected routing occurred.")
        print("    Check the classify_intent output.")

    print("=" * 64 + "\n")


if __name__ == "__main__":
    test_multitool_fallback()
