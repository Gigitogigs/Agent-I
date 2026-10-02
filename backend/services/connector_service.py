from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.connectors import CONNECTOR_CATALOG
from backend.db.models.settings import WorkspaceIntegration

async def list_connector_catalog(db: AsyncSession, workspace_id: UUID) -> List[dict]:
    stmt = select(WorkspaceIntegration).where(WorkspaceIntegration.workspace_id == workspace_id)
    result = await db.execute(stmt)
    configured_integrations = {k.integration_type: k for k in result.scalars().all()}
    
    out = []
    for connector_id, info in CONNECTOR_CATALOG.items():
        db_integ = configured_integrations.get(connector_id)
        
        config_fields = [
            {"name": k, "type": v["type"], "required": v["required"], "secret": v["secret"]}
            for k, v in info["config_schema"].items()
        ]
        
        is_configured = db_integ is not None
        status = db_integ.status if db_integ else None
        integration_id = db_integ.id if db_integ else None
        
        out.append({
            "id": connector_id,
            "display_name": info["display_name"],
            "domains": info["domains"],
            "transport": info["transport"],
            "config_fields": config_fields,
            "is_configured": is_configured,
            "status": status,
            "integration_id": integration_id
        })
    return out
