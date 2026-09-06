import uuid
import sys
import io
from pprint import pprint

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import HumanMessage
from root_agent.graph import root_agent

def run_query(query: str, session_id: str = None):
    if session_id is None:
        session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    print(f"\n==============================================")
    print(f"USER QUERY: {query}")
    print(f"SESSION ID: {session_id}")
    print(f"==============================================")
    
    state = {
        "messages": [HumanMessage(content=query)], 
        "session_id": session_id
    }
    
    # Run the graph
    result = root_agent.invoke(state, config=config)
    
    # Check if the graph was interrupted (e.g., by the escalation agent)
    graph_state = root_agent.get_state(config)
    if getattr(graph_state, 'next', None):
        print(f"\n⚠️ GRAPH PAUSED! Awaiting input for node(s): {graph_state.next}")
        
    last_msg = result["messages"][-1]
    print(f"\n[FINAL RESPONSE]:\n{last_msg.content}\n")
    
    print("--- Internal State ---")
    print(f"Subagent Results: {result.get('subagent_results')}")
    print(f"Risk Level: {result.get('risk_level')}")
    print(f"Requesting Agent: {result.get('requesting_agent')}")
    print("----------------------\n")


if __name__ == "__main__":
    print("Testing direct escalation (Intent -> Orchestrator -> Escalation Agent)...")
    run_query("I am furious, let me talk to a real human immediately!")

   # print("\nTesting knowledge retrieval (Intent -> Orchestrator -> Retrieval Agent -> Synthesize)...")
    #run_query("What is your refund policy for electronics?")

    print("\nTesting Tool use ")
    run_query("What is you =r refund policy? I want a refund of 3000$ on my last purchase.")