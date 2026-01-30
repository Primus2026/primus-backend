from app.services.alert_service import AlertService
from datetime import timedelta, datetime 
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.database.models.alert import Alert, AlertType
from app.schemas.alert import AlertCreate, AlertOut
from app.core import deps
from app.database.models.user import User
from fastapi import Body

router = APIRouter()

@router.post("/", response_model=AlertOut, status_code=201)
async def create_alert(
    alert_in: AlertCreate,
    db: AsyncSession = Depends(get_db),
    # We might want to secure this endpoint essentially for the "system" or "admin", 
    # but for now we'll leave it open or require a specific "service" user? 
    # The requirement didn't specify auth for the listener.
    # We'll assume for now it's internal or protected by network. 
    # Or we can reuse get_current_user if the listener logs in.
    # Given the description, we'll keep it simple:
):
    return await AlertService.create_alert(alert_in, db)

@router.post("/{alert_id}/resolve", response_model=AlertOut, status_code=200)
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Resolve an alert.
    """
    return await AlertService.resolve_alert(alert_id, db, user)

@router.get("/", response_model=list[AlertOut], status_code=200)
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Get all alerts.
    """
    return await AlertService.get_alerts(db)

@router.get("/unsent", response_model=list[AlertOut], status_code=200)
async def get_unsent_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Get all unsent alerts.
    """
    return await AlertService.get_unsent_alerts(db)

@router.post("/mark-as-read", response_model=list[AlertOut], status_code=200)
async def mark_alerts_as_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
    alert_ids: list[int] = Body(...),
    ):
    """
    Mark alerts as read.
    """
    return await AlertService.mark_alerts_as_read(alert_ids, db, user)