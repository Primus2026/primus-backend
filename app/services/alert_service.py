from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.alert import Alert
from app.schemas.alert import AlertCreate
from app.database.models.user import User
from fastapi import HTTPException
from datetime import datetime, timedelta

class AlertService:
    @staticmethod
    async def resolve_alert(
        alert_id: int,
        db: AsyncSession,
        user: User,
    ):
        alert = await db.get(Alert, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_resolved = True
        await db.commit()
        return alert

    @staticmethod
    async def create_alert(
        alert_in: AlertCreate,
        db: AsyncSession,
    ):
        # Check for existing unresolved alert
        stmt = select(Alert).where(
            Alert.rack_id == alert_in.rack_id,
            Alert.position_row == alert_in.position_row,
            Alert.position_col == alert_in.position_col,
            Alert.alert_type == alert_in.alert_type,
            Alert.is_resolved == False,
            Alert.created_at >= datetime.now() - timedelta(minutes=20)
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

    @staticmethod
    async def get_unsent_alerts(db: AsyncSession):
        stmt = select(Alert).where(
            Alert.is_sent == False,
            Alert.is_resolved == False
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_alerts(db: AsyncSession):
        stmt = select(Alert)
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def mark_alerts_as_read(alert_ids: list[int], db: AsyncSession, user: User):
        stmt = select(Alert).where(Alert.id.in_(alert_ids))
        result = await db.execute(stmt)
        alerts = result.scalars().all()
        for alert in alerts:
            alert.is_sent = True
        await db.commit()
        return alerts