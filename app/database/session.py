from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Async Session Configuration
async_engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession)

# Synchronous Session Configuration (for Celery tasks)
# Convert asyncpg URL to standard postgresql URL
sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
sync_engine = create_engine(sync_db_url)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

async def get_db():
    async with SessionLocal() as session:
        yield session
