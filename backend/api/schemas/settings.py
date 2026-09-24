from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationChannelBase(BaseModel):
    channel_type: str = Field(..., description="e.g., 'slack', 'email'")
    name: str = Field(..., description="Display name for the channel")
    config: Dict[str, Any] = Field(..., description="Configuration like webhook_url or email_address")
    is_active: bool = True

class NotificationChannelCreate(NotificationChannelBase):
    on_escalation: bool = True
    on_sla_breach: bool = True

class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    on_escalation: Optional[bool] = None
    on_sla_breach: Optional[bool] = None

class NotificationChannelOut(NotificationChannelBase):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    # Aggregated toggles from settings table
    on_escalation: bool
    on_sla_breach: bool

# ---------------------------------------------------------------------------
# Billing (Mocked)
# ---------------------------------------------------------------------------

class BillingUsage(BaseModel):
    ai_tokens_used: int
    ai_tokens_limit: int
    active_users: int
    users_limit: int

class InvoiceOut(BaseModel):
    id: str
    date: datetime
    amount: float
    status: str
    pdf_url: str

class BillingDetailsOut(BaseModel):
    plan_name: str
    stripe_customer_id: Optional[str]
    usage: BillingUsage
    invoices: List[InvoiceOut]

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

class IntegrationCreate(BaseModel):
    integration_type: str = Field(..., description="e.g., 'shopify', 'zendesk'")
    name: str = Field(..., description="Display name")
    config: Dict[str, Any] = Field(..., description="Credentials (e.g. {'api_key': '...'})")

class IntegrationOut(BaseModel):
    id: UUID
    workspace_id: UUID
    integration_type: str
    name: str
    status: str
    last_checked_at: Optional[datetime]
    created_at: datetime
    # We DO NOT include the `config` here to avoid exposing secrets
