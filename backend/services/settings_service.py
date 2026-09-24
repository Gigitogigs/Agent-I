from typing import List, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from fastapi import HTTPException, status

from backend.db.models.settings import (
    WorkspaceNotificationChannel,
    WorkspaceNotificationSetting,
    WorkspaceIntegration
)
from backend.db.models.workspace import Workspace
from backend.core.security import encrypt_secret, decrypt_secret
import json

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def get_notification_channels(db: AsyncSession, workspace_id: UUID) -> List[dict]:
    stmt = select(WorkspaceNotificationChannel).where(WorkspaceNotificationChannel.workspace_id == workspace_id)
    result = await db.execute(stmt)
    channels = result.scalars().all()
    
    out = []
    for c in channels:
        # Get settings for this channel
        st_stmt = select(WorkspaceNotificationSetting).where(
            WorkspaceNotificationSetting.workspace_id == workspace_id,
            WorkspaceNotificationSetting.channel_id == c.id
        )
        st_res = await db.execute(st_stmt)
        settings_list = st_res.scalars().all()
        
        on_escalation = any(s.is_enabled for s in settings_list if s.event_type == "escalation")
        on_sla_breach = any(s.is_enabled for s in settings_list if s.event_type == "sla_breach")
        
        out.append({
            "id": c.id,
            "workspace_id": c.workspace_id,
            "channel_type": c.channel_type,
            "name": c.name,
            "config": c.config,
            "is_active": c.is_active,
            "created_at": c.created_at,
            "on_escalation": on_escalation,
            "on_sla_breach": on_sla_breach
        })
    return out

async def create_notification_channel(db: AsyncSession, workspace_id: UUID, data: dict) -> dict:
    channel = WorkspaceNotificationChannel(
        workspace_id=workspace_id,
        channel_type=data["channel_type"],
        name=data["name"],
        config=data["config"],
        is_active=data.get("is_active", True)
    )
    db.add(channel)
    await db.flush()
    
    s1 = WorkspaceNotificationSetting(
        workspace_id=workspace_id,
        event_type="escalation",
        channel_id=channel.id,
        is_enabled=data.get("on_escalation", True)
    )
    s2 = WorkspaceNotificationSetting(
        workspace_id=workspace_id,
        event_type="sla_breach",
        channel_id=channel.id,
        is_enabled=data.get("on_sla_breach", True)
    )
    db.add_all([s1, s2])
    await db.commit()
    
    return {
        "id": channel.id,
        "workspace_id": channel.workspace_id,
        "channel_type": channel.channel_type,
        "name": channel.name,
        "config": channel.config,
        "is_active": channel.is_active,
        "created_at": channel.created_at,
        "on_escalation": s1.is_enabled,
        "on_sla_breach": s2.is_enabled
    }

async def update_notification_channel(db: AsyncSession, workspace_id: UUID, channel_id: UUID, data: dict) -> dict:
    channel = await db.scalar(select(WorkspaceNotificationChannel).where(
        WorkspaceNotificationChannel.id == channel_id,
        WorkspaceNotificationChannel.workspace_id == workspace_id
    ))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    if "name" in data and data["name"] is not None:
        channel.name = data["name"]
    if "config" in data and data["config"] is not None:
        channel.config = data["config"]
    if "is_active" in data and data["is_active"] is not None:
        channel.is_active = data["is_active"]
        
    # Update settings
    st_stmt = select(WorkspaceNotificationSetting).where(
        WorkspaceNotificationSetting.workspace_id == workspace_id,
        WorkspaceNotificationSetting.channel_id == channel.id
    )
    st_res = await db.execute(st_stmt)
    settings_list = st_res.scalars().all()
    
    on_escalation = next((s for s in settings_list if s.event_type == "escalation"), None)
    if on_escalation and "on_escalation" in data and data["on_escalation"] is not None:
        on_escalation.is_enabled = data["on_escalation"]
        
    on_sla_breach = next((s for s in settings_list if s.event_type == "sla_breach"), None)
    if on_sla_breach and "on_sla_breach" in data and data["on_sla_breach"] is not None:
        on_sla_breach.is_enabled = data["on_sla_breach"]
        
    await db.commit()
    
    return {
        "id": channel.id,
        "workspace_id": channel.workspace_id,
        "channel_type": channel.channel_type,
        "name": channel.name,
        "config": channel.config,
        "is_active": channel.is_active,
        "created_at": channel.created_at,
        "on_escalation": on_escalation.is_enabled if on_escalation else False,
        "on_sla_breach": on_sla_breach.is_enabled if on_sla_breach else False
    }

# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

async def get_billing_details(db: AsyncSession, workspace_id: UUID) -> dict:
    ws = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    # MOCK BILLING RESPONSE
    # TODO: Implement real Stripe SDK integration
    return {
        "plan_name": ws.plan.capitalize(),
        "stripe_customer_id": ws.stripe_customer_id,
        "usage": {
            "ai_tokens_used": 4500,
            "ai_tokens_limit": 10000,
            "active_users": 2,
            "users_limit": 5 if ws.plan == "free" else 100
        },
        "invoices": [
            {
                "id": "in_1mock2345",
                "date": datetime.now(timezone.utc),
                "amount": 0.0 if ws.plan == "free" else 29.0,
                "status": "paid",
                "pdf_url": "https://stripe.com/mock-invoice.pdf"
            }
        ]
    }

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

async def get_integrations(db: AsyncSession, workspace_id: UUID) -> List[dict]:
    stmt = select(WorkspaceIntegration).where(WorkspaceIntegration.workspace_id == workspace_id)
    res = await db.execute(stmt)
    integrations = res.scalars().all()
    
    # Exclude config from the returned dict for security
    return [
        {
            "id": i.id,
            "workspace_id": i.workspace_id,
            "integration_type": i.integration_type,
            "name": i.name,
            "status": i.status,
            "last_checked_at": i.last_checked_at,
            "created_at": i.created_at
        } for i in integrations
    ]

async def create_integration(db: AsyncSession, workspace_id: UUID, data: dict) -> dict:
    # Encrypt the config object as a JSON string
    config_str = json.dumps(data["config"])
    encrypted_config = encrypt_secret(config_str)
    
    integration = WorkspaceIntegration(
        workspace_id=workspace_id,
        integration_type=data["integration_type"],
        name=data["name"],
        config={"encrypted_payload": encrypted_config}, # store it under a key
        status="pending"
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    
    return {
        "id": integration.id,
        "workspace_id": integration.workspace_id,
        "integration_type": integration.integration_type,
        "name": integration.name,
        "status": integration.status,
        "last_checked_at": integration.last_checked_at,
        "created_at": integration.created_at
    }

async def delete_integration(db: AsyncSession, workspace_id: UUID, integration_id: UUID) -> None:
    integration = await db.scalar(select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == integration_id,
        WorkspaceIntegration.workspace_id == workspace_id
    ))
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
        
    await db.delete(integration)
    await db.commit()

async def verify_integration(db: AsyncSession, workspace_id: UUID, integration_id: UUID) -> dict:
    integration = await db.scalar(select(WorkspaceIntegration).where(
        WorkspaceIntegration.id == integration_id,
        WorkspaceIntegration.workspace_id == workspace_id
    ))
    
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
        
    # Decrypt config
    try:
        encrypted_payload = integration.config["encrypted_payload"]
        config_str = decrypt_secret(encrypted_payload)
        config_dict = json.loads(config_str)
    except Exception:
        integration.status = "failed"
        await db.commit()
        raise HTTPException(status_code=400, detail="Failed to decrypt integration credentials")
        
    itype = integration.integration_type.lower()
    success = False
    
    async with httpx.AsyncClient() as client:
        try:
            if itype == "shopify":
                # Expecting 'store_url' and 'access_token' in config
                store_url = config_dict.get("store_url", "").rstrip("/")
                token = config_dict.get("access_token", "")
                resp = await client.get(
                    f"{store_url}/admin/api/2024-01/shop.json",
                    headers={"X-Shopify-Access-Token": token},
                    timeout=10.0
                )
                success = (resp.status_code == 200)
            elif itype == "zendesk":
                # Expecting 'subdomain', 'email', 'api_token'
                sub = config_dict.get("subdomain", "")
                email = config_dict.get("email", "")
                token = config_dict.get("api_token", "")
                auth = (f"{email}/token", token)
                resp = await client.get(
                    f"https://{sub}.zendesk.com/api/v2/users/me.json",
                    auth=auth,
                    timeout=10.0
                )
                success = (resp.status_code == 200)
            else:
                # Custom MCP server - just mark active since we can't easily verify HTTP here unless it exposes a health check
                success = True
        except Exception:
            success = False
            
    if success:
        integration.status = "active"
        integration.last_checked_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "success", "message": "Integration verified and active"}
    else:
        integration.status = "failed"
        integration.last_checked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid credentials or endpoint unreachable")
