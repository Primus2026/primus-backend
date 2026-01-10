import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.user import User, UserRole
from app.core import security

BASE_URL = "api/v1/users"

# --- REGISTRATION TESTS ---

@pytest.mark.asyncio 
async def test_request_registration_success(async_client: AsyncClient, db_session: AsyncSession):
    user_in = {"login": "new_user", "email": "new@email.pl", "password": "testpassword"}
    response = await async_client.post(f"{BASE_URL}/request_register", json=user_in)
    
    assert response.status_code == 201
    data = response.json()
    assert data["login"] == "new_user"
    assert data["is_active"] is False
    assert data["role"] == "WAREHOUSEMAN"

@pytest.mark.asyncio
async def test_request_registration_invalid_data(async_client: AsyncClient):
    user_in = {"login": "only_login"} 
    response = await async_client.post(f"{BASE_URL}/request_register", json=user_in)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_request_registration_login_conflict(async_client: AsyncClient, db_session: AsyncSession):
    existing = User(login="taken", email="t@t.pl", password_hash="hash", role=UserRole.WAREHOUSEMAN)
    db_session.add(existing)
    await db_session.commit()

    user_in = {"login": "taken", "email": "other@email.pl", "password": "password"}
    response = await async_client.post(f"{BASE_URL}/request_register", json=user_in)
    assert response.status_code == 409
    assert response.json()["detail"] == "User with this login already exists"

# --- ADMIN CREATION ---

@pytest.mark.asyncio
async def test_create_admin_success(async_client: AsyncClient, db_session: AsyncSession):
    response = await async_client.post(f"{BASE_URL}/create_admin")
    assert response.status_code == 200
    
    result = await db_session.execute(select(User).where(User.role == UserRole.ADMIN))
    admin = result.scalars().first()
    assert admin is not None
    assert admin.is_active is True

# --- APPROVE USER TESTS ---

@pytest.mark.asyncio
async def test_approve_user_not_authorized(async_client: AsyncClient):
    response = await async_client.put(f"{BASE_URL}/approve_user/1")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_approve_user_not_enough_permissions(authorized_warehouseman_client: AsyncClient):
    response = await authorized_warehouseman_client.put(f"{BASE_URL}/approve_user/1")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_approve_user_not_found(authorized_admin_client: AsyncClient):
    response = await authorized_admin_client.put(f"{BASE_URL}/approve_user/9999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_approve_user_already_approved(authorized_admin_client: AsyncClient, db_session: AsyncSession):
    active_user = User(login="active", email="a@a.pl", is_active=True, password_hash="h", role=UserRole.WAREHOUSEMAN)
    db_session.add(active_user)
    await db_session.commit()
    await db_session.refresh(active_user)

    response = await authorized_admin_client.put(f"{BASE_URL}/approve_user/{active_user.id}")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_approve_user_success(authorized_admin_client: AsyncClient, db_session: AsyncSession):
    pending = User(login="pending", email="p@p.pl", is_active=False, password_hash="h", role=UserRole.WAREHOUSEMAN)
    db_session.add(pending)
    await db_session.commit()
    await db_session.refresh(pending)

    response = await authorized_admin_client.put(f"{BASE_URL}/approve_user/{pending.id}")
    assert response.status_code == 200
    
    await db_session.refresh(pending)
    assert pending.is_active is True

# --- REJECT (DELETE) USER TESTS ---

@pytest.mark.asyncio
async def test_delete_user_not_authorized(async_client: AsyncClient):
    response = await async_client.put(f"{BASE_URL}/reject_user/1")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_delete_user_not_enough_permissions(authorized_warehouseman_client: AsyncClient):
    response = await authorized_warehouseman_client.put(f"{BASE_URL}/reject_user/1")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_delete_user_not_found(authorized_admin_client: AsyncClient):
    response = await authorized_admin_client.put(f"{BASE_URL}/reject_user/9999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_user_already_approved(authorized_admin_client: AsyncClient, db_session: AsyncSession):
    active_user = User(login="active2", email="a2@a.pl", is_active=True, password_hash="h", role=UserRole.WAREHOUSEMAN)
    db_session.add(active_user)
    await db_session.commit()

    response = await authorized_admin_client.put(f"{BASE_URL}/reject_user/{active_user.id}")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_delete_user_success(authorized_admin_client: AsyncClient, db_session: AsyncSession):
    to_reject = User(login="to_reject", email="r@r.pl", is_active=False, password_hash="h", role=UserRole.WAREHOUSEMAN)
    db_session.add(to_reject)
    await db_session.commit()
    await db_session.refresh(to_reject)
    rej_id = to_reject.id

    response = await authorized_admin_client.put(f"{BASE_URL}/reject_user/{rej_id}")
    assert response.status_code == 200
    
    result = await db_session.execute(select(User).where(User.id == rej_id))
    assert result.scalars().first() is None