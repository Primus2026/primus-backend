from app.core.celery_worker import celery_app
from app.services.ai_service import AIService
from celery.utils.log import get_task_logger
import os
import asyncio
from app.database.session import SessionLocal
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.ai_tasks.retrain_model_task")
def retrain_model_task(self):
    """
    Celery task to retrain the AI model.
    """
    logger.info("Starting AI model retraining task...")
    try:
        # Since AIService.retrain_model is synchronous (modified by user), we can call it directly
        AIService.retrain_model()
        logger.info("AI model retraining completed successfully.")
        return {"status": "success", "message": "Model retraining completed"}
    except Exception as e:
        logger.error(f"Error during AI model retraining: {e}")
        # Re-raise the exception so Celery marks it as failed
        raise e


@celery_app.task(bind=True, name="app.tasks.ai_tasks.predict_task")
def predict_task(self, file_path: str):
    """
    Celery task to recognize a product from an image.
    """
    logger.info(f"Starting prediction task for file: {file_path}")

    # Pre-check file existence
    if not os.path.exists(file_path):
        logger.error(f"File not found at path: {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check file size
    file_size = os.path.getsize(file_path)
    logger.info(f"File size: {file_size} bytes")

    if file_size == 0:
        logger.error(f"File is empty: {file_path}")
        raise ValueError(f"File is empty: {file_path}")

    try:
        product_id, confidence = AIService.predict(file_path)

        if os.path.exists(file_path):
            os.remove(file_path)

        # Fetch product name from DB
        product_name = "Unknown"
        if product_id != -1:

            async def get_name():
                try:
                    async with SessionLocal() as session:
                        stmt = select(ProductDefinition).where(
                            ProductDefinition.id == product_id
                        )
                        result = await session.execute(stmt)
                        product = result.scalars().first()
                        return product.name if product else "Unknown"
                except Exception as e:
                    logger.error(f"Async DB fetch error: {e}")
                    return "Error"

            try:
                # Run the async function in a new event loop
                product_name = asyncio.run(get_name())
            except Exception as e:
                logger.error(f"Failed to run async loop: {e}")
                product_name = "Error"

        return {
            "product_id": product_id,
            "confidence": confidence,
            "name": product_name,
        }
    except Exception as e:
        logger.error(f"Error during prediction: {e}")
        raise e
