from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.database.models.alert import Alert, AlertType
from app.schemas.alert import AlertCreate, AlertOut
from app.core import deps
from app.database.models.user import User

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
    """
    Create a new alert (e.g. from MQTT Listener).
    """
    # Check for existing unresolved alert
    from sqlalchemy import select
    
    stmt = select(Alert).where(
        Alert.rack_id == alert_in.rack_id,
        Alert.position_row == alert_in.position_row,
        Alert.position_col == alert_in.position_col,
        Alert.alert_type == alert_in.alert_type,
        Alert.is_resolved == False
    )
    result = await db.execute(stmt)
    existing_alert = result.scalars().first()
    
    if existing_alert:
        return existing_alert

    alert = Alert(
        alert_type=alert_in.alert_type,
        rack_id=alert_in.rack_id,
        product_id=alert_in.product_id,
        message=alert_in.message,
        last_valid_weight=alert_in.last_valid_weight,
        position_row=alert_in.position_row,
        position_col=alert_in.position_col
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert
