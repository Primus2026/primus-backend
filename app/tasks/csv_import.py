import asyncio
from app.core.celery_worker import celery_app
from app.services.rack_service import RackService
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

async def process_import_async(file_content: bytes):
    # Create a local engine/session for this specific asyncio loop
    # This prevents "Future attached to a different loop" errors in Celery
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        try:
            return await RackService.process_csv_import(file_content, session)
        finally:
            await engine.dispose()

@celery_app.task(name="csv_import.import_racks")    
def import_racks(file_content: bytes):
    result = asyncio.run(process_import_async(file_content))
    return result.model_dump()