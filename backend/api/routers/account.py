from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db
from backend.api.schemas.workspace import PasswordConfirmBody
from backend.api.schemas.auth import MessageResponse
from backend.db.models.user import User
from backend.services.account_service import (
    schedule_account_deletion,
    cancel_account_deletion,
)

router = APIRouter(prefix="/account", tags=["account"])

@router.delete("", status_code=status.HTTP_202_ACCEPTED)
async def delete_account(
    body: PasswordConfirmBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await schedule_account_deletion(db, current_user, body.password)
    return MessageResponse(message="Account scheduled for deletion. You have been logged out.")

@router.post("/cancel-deletion")
async def restore_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await cancel_account_deletion(db, current_user)
    return MessageResponse(message="Account deletion cancelled.")
