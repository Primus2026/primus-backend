import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from app.database.models import User, UserRole
from app.core import security

from app.main import app
from app.database.session import get_db
from app.core.deps import get_redis
from app.database.models.base import Base
from app.core.config import settings

from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
import shutil
from app.core.storage.s3 import S3StorageProvider
# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session", autouse=True)
def override_media_root(tmp_path_factory):
    """Overrides MEDIA_ROOT to use a temporary directory for tests"""
    media_root = tmp_path_factory.mktemp("media")
    settings.MEDIA_ROOT = str(media_root)
    # Also override REPORT_DIR
    report_dir = tmp_path_factory.mktemp("reports")
    settings.REPORT_DIR = str(report_dir)
    return media_root

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine, class_=AsyncSession)

@pytest.fixture(scope="session")
async def db_engine():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    connection = await engine.connect()
    trans = await connection.begin()
    
    async with TestingSessionLocal(bind=connection) as session:
        yield session
        await session.close()

    await trans.rollback()
    await connection.close()
    
    app.dependency_overrides.clear()

@pytest.fixture
async def mock_redis():
    mock = AsyncMock()
    # Mock methods used in service
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=False)
    return mock


@pytest.fixture
async def async_client(db_session, mock_redis) -> AsyncGenerator[AsyncClient, None]:
    # Override the get_db dependency to use the test session
    async def override_get_db():
        yield db_session
        
    async def override_get_redis():
        yield mock_redis
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_token(db_session: AsyncSession) -> str:
    """Creates admin in database and returns his token"""
    admin = User(
        login="test_admin",
        email="admin@test.pl",
        password_hash=security.get_password_hash("test_pass"),
        role=UserRole.ADMIN,
        is_active=True 
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    return security.create_access_token(admin.id)

@pytest.fixture
async def warehouseman_token(db_session: AsyncSession) -> str:
    """Creates warehouseman and returns his token"""
    user = User(
        login="test_worker",
        email="worker@test.pl",
        password_hash=security.get_password_hash("test_pass"),
        role=UserRole.WAREHOUSEMAN,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    return security.create_access_token(user.id)

@pytest.fixture
async def authorized_admin_client(async_client: AsyncClient, admin_token: str) -> AsyncClient:
    async_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return async_client

@pytest.fixture
async def authorized_warehouseman_client(async_client: AsyncClient, warehouseman_token: str) -> AsyncClient:
    async_client.headers.update({"Authorization": f"Bearer {warehouseman_token}"})
    return async_client

@pytest.fixture
def s3_provider():
    with patch("aiobotocore.session.get_session") as mock_session:
        provider = S3StorageProvider()
        return provider

@pytest.fixture
def mock_storage():
    """Patches storage in AI Service"""
    with patch("app.services.ai_service.storage", new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def mock_yolo():
    with patch("ultralytics.YOLO") as mock:
        yield mock

@pytest.fixture
def mock_redis():
    with patch("app.core.redis_client.RedisClient.get_sync_client") as mock_sync, \
         patch("app.core.redis_client.RedisClient.get_client") as mock_async:
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_sync.return_value.lock.return_value = mock_lock
        yield mock_sync

@pytest.fixture
def temp_models_dir():
    # Create a temp dir for models
    d = tempfile.mkdtemp()
    old_dir = settings.MODELS_DIR
    settings.MODELS_DIR = d
    yield d
    # Cleanup
    settings.MODELS_DIR = old_dir
    shutil.rmtree(d)