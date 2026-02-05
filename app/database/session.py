from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False)

# Sync Session for Celery/Tools
SQLALCHEMY_DATABASE_URL_SYNC = settings.DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(SQLALCHEMY_DATABASE_URL_SYNC)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

async def get_db():
    async with SessionLocal() as session:
        yield session
