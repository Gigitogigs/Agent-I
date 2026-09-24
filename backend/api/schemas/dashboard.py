from typing import List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class UrgentApprovalOut(BaseModel):
    id: UUID
    action_type: str
    risk_level: str
    created_at: datetime
    
class DashboardStats(BaseModel):
    active_conversations_today: int
    pending_escalations: int
    unresolved_errors: int

class RecentConversationOut(BaseModel):
    id: UUID
    preview: Optional[str] = None
    status: str
    updated_at: datetime

class SystemHealth(BaseModel):
    integrations_status: str

class HomepageSummaryOut(BaseModel):
    urgent_approvals: List[UrgentApprovalOut]
    stats: DashboardStats
    recent_conversations: List[RecentConversationOut]
    health: SystemHealth
