from app.core.celery_worker import celery_app
from app.services.ai_service import AIService
from celery.utils.log import get_task_logger
import os
import asyncio
from app.database.session import SyncSessionLocal
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from app.core.config import settings

import tempfile
import uuid
import asyncio
import aiofiles
from app.core.storage import storage

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.ai_tasks.retrain_model_task")
def retrain_model_task(self):
    """
    Celery task to retrain the AI model.
    """
    logger.info("Starting AI model retraining task...")
    try:
        AIService.retrain_model()
        logger.info("AI model retraining completed successfully.")
        return {"status": "success", "message": "Model retraining completed"}
    except Exception as e:
        logger.error(f"Error during AI model retraining: {e}")
        # Re-raise the exception so Celery marks it as failed
        raise e


def fetch_product_details(product_id: int) -> tuple[str, str]:
    # Sync DB fetch
    try:
        with SyncSessionLocal() as session:
            stmt = select(ProductDefinition).where(ProductDefinition.id == product_id)
            product = session.execute(stmt).scalars().first()
            if product:
                return product.name, product.barcode
            return "Unknown", ""
    except Exception as e:
        logger.error(f"DB fetch error: {e}")
        return "Error", ""

@celery_app.task(bind=True, name="app.tasks.ai_tasks.predict_task")
def predict_task(self, s3_key: str):
    """
    Celery task to recognize a product from an image.
    Receives s3_key, downloads it, predicts, cleans up.
    """
    logger.info(f"Starting prediction task for key: {s3_key}")
    

    
    # Download to temp
    ext = os.path.splitext(s3_key)[1]
    if not ext: ext = ".jpg"
    
    temp_file = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}{ext}")
    
    async def download_file():
        content = await storage.get(s3_key)
        async with aiofiles.open(temp_file, "wb") as f:
            await f.write(content)
            
    async def delete_s3_file():
        await storage.delete(s3_key)

    try:
        # 1. Download
        asyncio.run(download_file())
        
        if not os.path.exists(temp_file):
             raise FileNotFoundError(f"Failed to download {s3_key}")
        
        # 2. Predict
        product_id, confidence = AIService.predict(temp_file)

        # 3. Cleanup local
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        # 4. Cleanup S3? 
        # API uploaded to 'temp_uploads' or similar. 
        # For this flow, we should probably delete the source file from S3 too.
        asyncio.run(delete_s3_file())

        # Fetch product details from DB (Sync)
        product_name = "Unknown"
        product_barcode = ""
        if product_id != -1:
            product_name, product_barcode = fetch_product_details(product_id)

        return {
            "product_id": product_id,
            "confidence": confidence,
            "name": product_name,
            "barcode": product_barcode,
        }
    except Exception as e:
        logger.error(f"Error during prediction: {e}")
        raise e
