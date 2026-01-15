import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from app.database.models import User, UserRole
from app.core import security

from app.main import app
from app.database.session import get_db
from app.database.models.base import Base
from app.core.config import settings

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session", autouse=True)
def override_media_root(tmp_path_factory):
    """Overrides MEDIA_ROOT to use a temporary directory for tests"""
    media_root = tmp_path_factory.mktemp("media")
    settings.MEDIA_ROOT = str(media_root)
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
@pytest.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    # Override the get_db dependency to use the test session
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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