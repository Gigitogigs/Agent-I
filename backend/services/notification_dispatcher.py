import json
import logging
from uuid import UUID
from enum import Enum
from typing import Callable, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.models.settings import WorkspaceNotificationChannel, WorkspaceNotificationSetting
from backend.services.settings_service import _decrypt_cfg

logger = logging.getLogger(__name__)

class ProviderEnum(str, Enum):
    slack   = "slack"
    teams   = "teams"
    discord = "discord"
    email   = "email"

PROVIDERS: Dict[ProviderEnum, Callable[[Dict[str, Any], Dict[str, Any]], None]] = {}

def register(provider: ProviderEnum):
    def decorator(fn):
        PROVIDERS[provider] = fn
        return fn
    return decorator

@register(ProviderEnum.slack)
def send_slack(cfg: Dict[str, Any], payload: Dict[str, Any]):
    import requests
    text = (
        f":rotating_light: *HITL Approval Required*\n"
        f"Risk: {payload.get('risk_level', 'UNKNOWN')}\n"
        f"Session: `{payload.get('session_id')}`\n"
        f"Checkpoint: `{payload.get('checkpoint_id')}`\n"
        f"Workspace: `{payload.get('workspace_id')}`\n"
        f"Please review in the dashboard."
    )
    resp = requests.post(cfg["webhook_url"], json={"text": text}, timeout=10)
    resp.raise_for_status()

@register(ProviderEnum.teams)
def send_teams(cfg: Dict[str, Any], payload: Dict[str, Any]):
    import requests
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": "🚨 HITL Approval Required", "weight": "bolder", "size": "large"},
                    {"type": "FactSet", "facts": [
                        {"title": "Risk Level", "value": payload.get("risk_level", "UNKNOWN")},
                        {"title": "Session ID", "value": str(payload.get("session_id"))},
                        {"title": "Checkpoint ID", "value": str(payload.get("checkpoint_id"))},
                        {"title": "Workspace", "value": str(payload.get("workspace_id"))},
                    ]},
                ]
            }
        }]
    }
    resp = requests.post(cfg["webhook_url"], json=card, timeout=10)
    resp.raise_for_status()

@register(ProviderEnum.discord)
def send_discord(cfg: Dict[str, Any], payload: Dict[str, Any]):
    import requests
    content = (
        f"🚨 **HITL Approval Required**\n"
        f"**Risk:** {payload.get('risk_level', 'UNKNOWN')}\n"
        f"**Session:** `{payload.get('session_id')}`\n"
        f"**Workspace:** `{payload.get('workspace_id')}`\n"
        f"Please review in the dashboard."
    )
    resp = requests.post(cfg["webhook_url"], json={"content": content}, timeout=10)
    resp.raise_for_status()

@register(ProviderEnum.email)
def send_email(cfg: Dict[str, Any], payload: Dict[str, Any]):
    import smtplib
    import email.message
    msg = email.message.EmailMessage()
    msg["Subject"] = f"[HITL] Approval Required – Risk: {payload.get('risk_level', 'UNKNOWN')}"
    msg["From"]    = cfg["sender"]
    msg["To"]      = cfg["recipient"]
    msg.set_content(
        f"A HIT-L approval is required.\n\n"
        f"Workspace ID : {payload.get('workspace_id')}\n"
        f"Session ID   : {payload.get('session_id')}\n"
        f"Risk Level   : {payload.get('risk_level', 'UNKNOWN')}\n"
        f"Checkpoint   : {payload.get('checkpoint_id')}\n\n"
        f"Please log into the dashboard to review and approve or reject."
    )
    with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587))) as s:
        s.ehlo()
        # s.starttls() might fail if not supported, but AWS SES supports it
        s.starttls()
        s.login(cfg["smtp_user"], cfg["smtp_password"])
        s.send_message(msg)

async def dispatch(event_type: str, workspace_id: UUID, payload: dict, db: AsyncSession) -> None:
    stmt = (
        select(WorkspaceNotificationChannel, WorkspaceNotificationSetting)
        .join(WorkspaceNotificationSetting, WorkspaceNotificationChannel.id == WorkspaceNotificationSetting.channel_id)
        .where(
            WorkspaceNotificationChannel.workspace_id == workspace_id,
            WorkspaceNotificationChannel.is_active == True,
            WorkspaceNotificationSetting.event_type == event_type,
            WorkspaceNotificationSetting.is_enabled == True,
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    for channel, _ in rows:
        try:
            cfg = _decrypt_cfg(channel)
            provider = ProviderEnum(channel.channel_type)
            if provider in PROVIDERS:
                PROVIDERS[provider](cfg, {"workspace_id": str(workspace_id), **payload})
                logger.info("Notification sent via %s for workspace %s", provider, workspace_id)
            else:
                logger.warning("Unknown notification provider: %s", channel.channel_type)
        except Exception as exc:
            logger.error(
                "Failed to send notification via channel %s (%s): %s",
                channel.id, channel.channel_type, exc, exc_info=True
            )
            # TODO: push to notifications_deadletter queue for retry
