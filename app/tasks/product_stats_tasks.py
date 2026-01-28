from app.core.celery_worker import celery_app
from app.services.product_stats_service import ProductStatsService
from app.database.session import SessionLocal
import asyncio

async def _update_frequencies_async():
    async with SessionLocal() as db:
        await ProductStatsService.update_products_frequencies(db)

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@celery_app.task
def update_frequencies_task():
    """
    Background task to update product frequency classes (ABC analysis).
    """
    return run_async(_update_frequencies_async())
