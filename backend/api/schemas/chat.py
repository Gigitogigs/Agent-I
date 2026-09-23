from typing import Optional, Dict, Any, List
from datetime import datetime
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


class ConversationTurnOut(BaseModel):
    id: UUID
    speaker: str = Field(alias="role")
    text: Optional[str] = Field(alias="content")
    timestamp: datetime = Field(alias="created_at")
    agentId: Optional[str] = Field(alias="agent_id", default=None)

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }


class ConversationOut(BaseModel):
    id: UUID
    status: str
    customerId: Optional[str] = Field(alias="customer_identifier", default=None)
    customerName: Optional[str] = Field(alias="customer_name", default=None)
    summary: Optional[str] = None
    agentsInvolved: List[str] = Field(default_factory=list)
    lastUpdatedAt: datetime = Field(alias="updated_at")

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }


class ConversationDetailOut(ConversationOut):
    createdAt: datetime = Field(alias="created_at")
    transcript: List[ConversationTurnOut] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    items: List[ConversationOut]
    nextCursor: Optional[str] = None
