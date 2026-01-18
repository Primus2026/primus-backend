from datetime import datetime, timedelta
from typing import List
from celery import shared_task
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.database.models.rack import Rack
from app.database.models.alert import Alert
from app.services.report_service import ReportService
from app.services.report_storage import ReportStorageService
from app.core.celery_worker import celery_app

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import settings

async def process_expiry_report_async(task_id: str, rack_id: int | None = None, barcode: str | None = None):

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

async def process_audit_report_async(task_id: str):
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. Fetch Racks (for fill percentage)
            stmt_racks = select(Rack).options(selectinload(Rack.items))
            racks_result = await db.execute(stmt_racks)
            racks = racks_result.scalars().all()
            
            # 2. Product Audit (Inventory)
            stmt_items = select(StockItem).options(
                selectinload(StockItem.product),
                selectinload(StockItem.rack),
                selectinload(StockItem.receiver)
            )
            
            items_result = await db.execute(stmt_items)
            items = items_result.scalars().all()
            
            # 3. Alerts (Unresolved)
            stmt_alerts = select(Alert).where(Alert.is_resolved == False).options(
                selectinload(Alert.rack),
                selectinload(Alert.product)
            ).order_by(Alert.created_at.desc())
             
            alerts_result = await db.execute(stmt_alerts)
            alerts = alerts_result.scalars().all()

            # 4. Generate PDF
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"AUDIT_{timestamp}_{task_id}.pdf"
            # Use ReportStorageService to get path
            filepath = ReportStorageService._validate_path(filename)
            
            ReportService.generate_audit_pdf(racks, items, alerts, filepath)
            
            return {"filename": filename}
        
        except Exception as e:
            print(f"Error generating audit report: {e}")
            raise e
        finally:
            await engine.dispose() 

@celery_app.task(bind=True)
def generate_expiry_report_task(self,rack_id: int | None = None, barcode: str | None = None):
    """
    Background task to generate expiry report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return asyncio.run(process_expiry_report_async(task_id, rack_id, barcode))

@celery_app.task(bind=True)
def generate_audit_report_task(self):
    """
    Background task to generate audit report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return asyncio.run(process_audit_report_async(task_id))

@celery_app.task
def cleanup_old_reports_task():
    """
    Deletes reports older than 7 days.
    """
    count = ReportStorageService.cleanup_old_reports(days=7)
    return {"deleted_count": count}
