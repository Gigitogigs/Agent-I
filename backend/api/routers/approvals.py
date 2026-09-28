from typing import List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, Query, status, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.arq import get_arq_redis

from backend.api.dependencies import get_current_user, get_db, require_min_role
from backend.api.schemas.approval import ApprovalOut, ApprovalRejectBody
from backend.api.schemas.auth import MessageResponse
from backend.db.models.user import User
from backend.services.approval_service import (
    list_approvals,
    approve_request,
    reject_request,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["approvals"])

@router.get("", response_model=List[ApprovalOut])
async def get_approvals(
    workspace_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED, ALL)"),
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("operator"))
):
    return await list_approvals(db, workspace_id, status)

@router.post("/{app_id}/approve", status_code=status.HTTP_200_OK)
async def approve_approval(
    workspace_id: UUID,
    app_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_min_role("operator")),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    redis = await get_arq_redis()
    cache_key = None
    if idempotency_key:
        cache_key = f"idemp:approve:{idempotency_key}"
        cached = await redis.get(cache_key)
        if cached:
            if cached == b"in_progress":
                raise HTTPException(status_code=409, detail="Request in progress")
            return json.loads(cached)
            
        acquired = await redis.set(cache_key, "in_progress", nx=True, ex=86400)
        if not acquired:
            raise HTTPException(status_code=409, detail="Request in progress")

    try:
        await approve_request(db, workspace_id, app_id, current_user)
        resp = MessageResponse(message="Request approved successfully.")
        if cache_key:
            await redis.set(cache_key, resp.model_dump_json(), ex=86400)
        return resp
    except Exception as e:
        if cache_key:
            await redis.delete(cache_key)
        raise e

@router.post("/{app_id}/reject", status_code=status.HTTP_200_OK)
async def reject_approval(
    workspace_id: UUID,
    app_id: UUID,
    body: ApprovalRejectBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_min_role("operator")),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    redis = await get_arq_redis()
    cache_key = None
    if idempotency_key:
        cache_key = f"idemp:reject:{idempotency_key}"
        cached = await redis.get(cache_key)
        if cached:
            if cached == b"in_progress":
                raise HTTPException(status_code=409, detail="Request in progress")
            return json.loads(cached)
            
        acquired = await redis.set(cache_key, "in_progress", nx=True, ex=86400)
        if not acquired:
            raise HTTPException(status_code=409, detail="Request in progress")

    try:
        await reject_request(db, workspace_id, app_id, body.reason, current_user)
        resp = MessageResponse(message="Request rejected successfully.")
        if cache_key:
            await redis.set(cache_key, resp.model_dump_json(), ex=86400)
        return resp
    except Exception as e:
        if cache_key:
            await redis.delete(cache_key)
        raise e
