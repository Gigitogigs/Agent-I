from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from uuid import UUID

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationChannelBase(BaseModel):
    channel_type: Literal["slack", "teams", "discord", "email"] = Field(..., description="e.g., 'slack', 'email'")
    name: str = Field(..., description="Display name for the channel")
    config: Dict[str, Any] = Field(..., description="Configuration like webhook_url or email_address")
    is_active: bool = True

class NotificationChannelCreate(NotificationChannelBase):
    on_escalation: bool = True
    on_sla_breach: bool = True

    @model_validator(mode='after')
    def validate_config_keys(self):
        ct = self.channel_type
        cfg = self.config or {}
        required = []
        if ct in ["slack", "teams", "discord"]:
            required = ["webhook_url"]
        elif ct == "email":
            required = ["smtp_host", "smtp_user", "smtp_password", "sender", "recipient"]
            
        missing = [k for k in required if k not in cfg]
        if missing:
            raise ValueError(f"{ct} config missing keys: {missing}")
        return self

class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    on_escalation: Optional[bool] = None
    on_sla_breach: Optional[bool] = None

class NotificationChannelOut(BaseModel):
    id: UUID
    workspace_id: UUID
    channel_type: Literal["slack", "teams", "discord", "email"]
    name: str
    is_active: bool
    created_at: datetime
    # Aggregated toggles from settings table
    on_escalation: bool
    on_sla_breach: bool
    has_config: bool = True

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
