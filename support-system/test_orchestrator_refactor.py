import uuid
import sys
import io
import asyncio
from pprint import pprint
from langgraph.types import Command

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import HumanMessage
from root_agent.graph import root_agent

def test_fan_out_integration():
    print("\n--- Running Fan-out Integration Test ---")
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    
    from unittest.mock import patch, MagicMock
    from root_agent.router import RouterDecision
    
    mock_decision = RouterDecision(
        intents=["faq", "order_action"],
        urgency="LOW",
        requires_human=False
    )
    
    with patch("root_agent.graph.get_router_decision", return_value=mock_decision):
        state = {
            "messages": [HumanMessage(content="What is your return policy, and also cancel order 123")], 
            "session_id": session_id
        }
        
        with patch("root_agent.graph.validate_action", return_value="LOW"):
            with patch("root_agent.graph.invoke_retrieval_agent", MagicMock()) as mock_retrieval_tool:
                with patch("root_agent.graph.invoke_action_agent", MagicMock()) as mock_action_tool:
                    class MockRetrievalResult:
                        def __init__(self):
                            self.answer = "Mocked answer"
                            self.source_chunks = ["chunk1"]
                    mock_retrieval_tool.invoke.return_value = MockRetrievalResult()
                    
                    class MockActionResult:
                        def model_dump(self):
                            return {"success": True, "data": "Mocked action"}
                    mock_action_tool.invoke.return_value = MockActionResult()
                    
                    result = root_agent.invoke(state, config=config)
                    
                    subagent_results = result.get("subagent_results", {})
                    assert "retrieval" in subagent_results, "Missing retrieval results from fan-out"
                    assert "action" in subagent_results, "Missing action results from fan-out"
                    
                    assert "context_slice" in result
                    print("✅ Fan-out Integration Test Passed!")

def test_interrupt_resume():
    print("\n--- Running Interrupt/Resume Test ---")
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    
    from unittest.mock import patch, MagicMock, MagicMock
    from root_agent.router import RouterDecision
    
    mock_decision = RouterDecision(
        intents=["order_action"],
        urgency="HIGH",
        requires_human=False
    )
    
    with patch("root_agent.graph.get_router_decision", return_value=mock_decision):
        with patch("root_agent.graph.validate_action", return_value="HIGH"):
            state = {
                "messages": [HumanMessage(content="Refund $1000")], 
                "session_id": session_id
            }
            
            # Graph runs and pauses at interrupt()
            result = root_agent.invoke(state, config=config)
            
            graph_state = root_agent.get_state(config)
            assert graph_state.next, "Graph should be paused!"
            assert "guardrail_check" in graph_state.next, f"Graph should be paused inside guardrail_check, instead in: {graph_state.next}"
            
            print("Graph paused successfully.")
            
            # Resume with approval
            resume_command = Command(resume={"status": "approved"})
            
            with patch("root_agent.graph.invoke_action_agent", MagicMock()) as mock_action_tool:
                mock_action_tool.invoke.return_value = {"success": True, "data": "Mocked Action Result"}
                
                result2 = root_agent.invoke(resume_command, config=config)
                
                mock_action_tool.invoke.assert_called_once()
                subagent_results = result2.get("subagent_results", {})
                assert "action" in subagent_results, "Action should have run after approval"
                assert subagent_results["action"].get("success") == True, "Action should be successful"
                
                print("✅ Interrupt/Resume Test Passed!")

def test_guardrail_reality():
    print("\n--- Running Guardrail-Reality Test ---")
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    
    from unittest.mock import patch, MagicMock
    from root_agent.router import RouterDecision
    
    mock_decision = RouterDecision(
        intents=["order_action"],
        urgency="LOW",
        requires_human=False
    )
    
    with patch("root_agent.graph.get_router_decision", return_value=mock_decision):
        with patch("root_agent.graph.validate_action", return_value="LOW") as mock_validate:
            with patch("root_agent.graph.invoke_action_agent", MagicMock()) as mock_action_tool:
                # We need a proper mock object that returns something when model_dump() is called
                class MockResult:
                    def model_dump(self):
                        return {"success": True}
                mock_action_tool.invoke.return_value = MockResult()
                
                state = {
                    "messages": [HumanMessage(content="Issue refund")], 
                    "session_id": session_id
                }
                
                root_agent.invoke(state, config=config)
                
                guardrail_payload = mock_validate.call_args[0][0]
                action_payload_kwargs = mock_action_tool.invoke.call_args[0][0]
                
                action_type = action_payload_kwargs.get("action_type")
                params = action_payload_kwargs.get("params")
                
                action_payload = {"action_type": action_type, "params": params}
                
                assert guardrail_payload == action_payload, f"Mismatch!\nGuardrail validated: {guardrail_payload}\nAction received: {action_payload}"
                
                print("✅ Guardrail-Reality Test Passed!")

if __name__ == "__main__":
    try:
        test_fan_out_integration()
    except AssertionError as e:
        print(f"❌ Fan-out Integration Test Failed: {e}")
        
    try:
        test_interrupt_resume()
    except AssertionError as e:
        print(f"❌ Interrupt/Resume Test Failed: {e}")
        
    try:
        test_guardrail_reality()
    except AssertionError as e:
        print(f"❌ Guardrail-Reality Test Failed: {e}")
