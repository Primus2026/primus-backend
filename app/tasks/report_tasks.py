from datetime import datetime, timedelta
from typing import List
from celery import shared_task
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.services.report_service import ReportService
from app.services.report_storage import ReportStorageService
from app.core.celery_worker import celery_app

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import settings

async def process_expiry_report_async(task_id: str, rack_id: int | None = None, barcode: str | None = None):
    # Create a local engine/session for this specific asyncio loop
    # consistently with product_definition_tasks.py
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. Query Data: Items expiring within 24h or already expired
            now = datetime.now()
            threshold = now + timedelta(hours=24)
            # Using select() for AsyncSession
            stmt = select(StockItem).join(ProductDefinition).filter(
                StockItem.expiry_date <= threshold
            )
            
            if rack_id:
                stmt = stmt.where(StockItem.rack_id == rack_id)
            
            if barcode:
                stmt = stmt.where(ProductDefinition.barcode == barcode)
            
            stmt = stmt.options(
                selectinload(StockItem.product),
                selectinload(StockItem.rack)
            )
            result = await db.execute(stmt)
            items = result.scalars().all()

            # 2. Determine Filename
            timestamp = now.strftime("%Y%m%d")
            filename = f"EXPIRY_{timestamp}_{task_id}.pdf"
            filepath = ReportStorageService._validate_path(filename)

            # 3. Generate PDF
            ReportService.generate_expiry_pdf(items, filepath)

            return {"filename": filename}
        finally:
            await engine.dispose()

@celery_app.task(bind=True)
def generate_expiry_report_task(self, user_id: int, rack_id: int | None = None, barcode: str | None = None):
    """
    Background task to generate expiry report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return asyncio.run(process_expiry_report_async(task_id, rack_id, barcode))

@celery_app.task
def scheduled_expiry_check_task():
    """
    Scheduled task (e.g. daily) to trigger the report generation system-wide.
    """
    # Use a system user ID (e.g., 0 or 1) or handle logically
    # For now we just trigger the task
    generate_expiry_report_task.delay(user_id=1) 

@celery_app.task
def cleanup_old_reports_task():
    """
    Deletes reports older than 7 days.
    """
    count = ReportStorageService.cleanup_old_reports(days=7)
    return {"deleted_count": count}
