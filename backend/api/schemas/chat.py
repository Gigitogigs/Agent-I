from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The customer's message to the agent.")
    
class ChatResponse(BaseModel):
    response: str = Field(..., description="The final synthesised response from the Orchestrator LLM.")
    turnId: UUID = Field(alias="turn_id", description="The ID of the recorded conversation turn.")
    subagentResults: Optional[Dict[str, Any]] = Field(alias="subagent_results", default=None, description="Structured results from any subagents invoked during the turn.")
    
    model_config = {
        "populate_by_name": True
    }
