from datetime import datetime, timedelta
from typing import List
from pathlib import Path

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
import os
import tempfile
import aiofiles

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

async def _process_expiry_report_async(task_id: str, rack_id: int | None = None, barcode: str | None = None):
    try:
        async with SessionLocal() as db:
            # 1. Query Data: Items expiring within 24h or already expired
            now = datetime.now()
            threshold = now + timedelta(hours=24)
            
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
            
            # 3. Generate PDF to Temp File
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                temp_path = Path(tmp.name)
            
            try:
                # Report generation is CPU-bound (ReportLab), so we can run it in a thread or just synchronously 
                # since it doesn't block the async loop significantly for small reports, 
                # but better to keep it as is.
                ReportService.generate_expiry_pdf(items, temp_path)
                
                # 4. Upload to Storage (Async)
                async with aiofiles.open(temp_path, "rb") as f:
                    content = await f.read()
                    await ReportStorageService.save_report(filename, content)
                
            finally:
                if temp_path.exists():
                    os.remove(temp_path)

            return {"filename": filename}
    except Exception as e:
        print(f"Error generating expiry report: {e}")
        raise e

def process_expiry_report(task_id: str, rack_id: int | None = None, barcode: str | None = None):
    return run_async(_process_expiry_report_async(task_id, rack_id, barcode))

async def _process_audit_report_async(task_id: str):
    try:
        async with SessionLocal() as db:
            # 1. Fetch Racks (for fill percentage)
            stmt_racks = select(Rack).options(selectinload(Rack.items))
            result_racks = await db.execute(stmt_racks)
            racks = result_racks.scalars().all()
            
            # 2. Product Audit (Inventory)
            stmt_items = select(StockItem).options(
                selectinload(StockItem.product),
                selectinload(StockItem.rack),
                selectinload(StockItem.receiver)
            )
            result_items = await db.execute(stmt_items)
            items = result_items.scalars().all()
            
            # 3. Alerts (Unresolved)
            stmt_alerts = select(Alert).where(Alert.is_resolved == False).options(
                selectinload(Alert.rack),
                selectinload(Alert.product)
            ).order_by(Alert.created_at.desc())
            result_alerts = await db.execute(stmt_alerts)
            alerts = result_alerts.scalars().all()

            # 4. Generate PDF
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"AUDIT_{timestamp}_{task_id}.pdf"
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                temp_path = Path(tmp.name)
            
            try:
                ReportService.generate_audit_pdf(racks, items, alerts, temp_path)
                
                async with aiofiles.open(temp_path, "rb") as f:
                    content = await f.read()
                    await ReportStorageService.save_report(filename, content)
                
            finally:
                if temp_path.exists():
                    os.remove(temp_path)
            
            return {"filename": filename}
        
    except Exception as e:
        print(f"Error generating audit report: {e}")
        raise e

def process_audit_report(task_id: str):
    return run_async(_process_audit_report_async(task_id))

async def _process_temp_report_async(task_id: str, rack_id: int | None = None, barcode: str | None = None):
    try:
        async with SessionLocal() as db:
            # 1. Query Data: Temp Alerts
            from app.schemas.alert import AlertType
            stmt = select(Alert).where(Alert.alert_type == AlertType.TEMP).order_by(Alert.created_at.desc())
            
            if rack_id:
                stmt = stmt.where(Alert.rack_id == rack_id)
            
            # Note: Filtering alerts by barcode is tricky as Alert has product_id, not barcode directly.
            # But we can join ProductDefinition.
            if barcode:
                stmt = stmt.join(Alert.product).where(ProductDefinition.barcode == barcode)
            
            stmt = stmt.options(
                selectinload(Alert.rack),
                selectinload(Alert.product)
            )
            
            result = await db.execute(stmt)
            alerts = result.scalars().all()

            # 2. Determine Filename
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"TEMP_{timestamp}_{task_id}.pdf"
            
            # 3. Generate PDF to Temp File
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                temp_path = Path(tmp.name)
            
            try:
                ReportService.generate_temp_pdf(alerts, temp_path)
                
                # 4. Upload to Storage (Async)
                async with aiofiles.open(temp_path, "rb") as f:
                    content = await f.read()
                    await ReportStorageService.save_report(filename, content)
                
            finally:
                if temp_path.exists():
                    os.remove(temp_path)

            return {"filename": filename}
    except Exception as e:
        print(f"Error generating temp report: {e}")
        raise e

def process_temp_report(task_id: str, rack_id: int | None = None, barcode: str | None = None):
    return run_async(_process_temp_report_async(task_id, rack_id, barcode))


@celery_app.task(bind=True)
def generate_expiry_report_task(self,rack_id: int | None = None, barcode: str | None = None):
    """
    Background task to generate expiry report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return process_expiry_report(task_id, rack_id, barcode)

@celery_app.task(bind=True)
def generate_audit_report_task(self):
    """
    Background task to generate audit report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return process_audit_report(task_id)

@celery_app.task(bind=True)
def generate_temp_report_task(self, rack_id: int | None = None, barcode: str | None = None):
    """
    Background task to generate temperature report.
    Returns: {"filename": "..."}
    """
    task_id = self.request.id
    return process_temp_report(task_id, rack_id, barcode)

@celery_app.task
def cleanup_old_reports_task():
    """
    Deletes reports older than 7 days.
    """
    return run_async(ReportStorageService.cleanup_old_reports(days=7))
