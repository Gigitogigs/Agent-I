from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class HitlBreakpoint(BaseModel):
    id: str
    label: str
    expiryBehavior: str
    slaWindowMins: int

class AgentDetail(BaseModel):
    id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    fallbackModel: Optional[str] = None
    systemPrompt: Optional[str] = None
    tools: Optional[List[str]] = None
    guardrails: Optional[Dict[str, Any]] = None
    hitlBreakpoints: Optional[List[HitlBreakpoint]] = None
    apiKeyHint: Optional[str] = None

class AgentConfigOut(BaseModel):
    global_: AgentDetail = Field(alias="global")
    orchestrator: AgentDetail
    retrieval: AgentDetail
    action: AgentDetail
    escalation: AgentDetail

    class Config:
        populate_by_name = True

class AgentConfigUpdate(BaseModel):
    model: Optional[str] = None
    fallbackModel: Optional[str] = None
    systemPrompt: Optional[str] = None
    tools: Optional[List[str]] = None
    guardrails: Optional[Dict[str, Any]] = None
    hitlBreakpoints: Optional[List[HitlBreakpoint]] = None

class ApiKeyUpdate(BaseModel):
    apiKey: str
    provider: str

class ApiKeyResponse(BaseModel):
    apiKeyHint: str
