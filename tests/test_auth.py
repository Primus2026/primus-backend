import pytest
from httpx import AsyncClient
from app.core.security import get_password_hash
import pyotp
from app.database.models.user import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession

# --- FIXTURES ---

@pytest.fixture
async def auth_user(db_session: AsyncSession):
    password = "secret_password"
    hashed_pw = get_password_hash(password)
    user = User(
        login="testauth",
        email="auth@test.com",
        password_hash=hashed_pw,
        role=UserRole.WAREHOUSEMAN,
        is_2fa_enabled=False,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def inactive_user(db_session: AsyncSession):
    password = "secret_password"
    hashed_pw = get_password_hash(password)
    user = User(
        login="inactive_auth",
        email="inactive@test.com",
        password_hash=hashed_pw,
        role=UserRole.WAREHOUSEMAN,
        is_2fa_enabled=False,
        is_active=False
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

# --- LOGIN TESTS ---

@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, auth_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": auth_user.login, "password": "secret_password"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["is_2fa_required"] is False

@pytest.mark.asyncio
async def test_login_incorrect_password(async_client: AsyncClient, auth_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": auth_user.login, "password": "wrong_password"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect login or password"

@pytest.mark.asyncio
async def test_login_inactive_user(async_client: AsyncClient, inactive_user: User):
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": inactive_user.login, "password": "secret_password"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Inactive user"

@pytest.mark.asyncio
async def test_access_me_without_token(async_client: AsyncClient):
    response = await async_client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

# --- 2FA TESTS ---

@pytest.mark.asyncio
async def test_2fa_setup_flow(async_client: AsyncClient, auth_user: User):
    # 1. Login
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        data={"username": auth_user.login, "password": "secret_password"}
    )
    token = login_resp.json()["access_token"]

    # 2. Setup 2FA
    setup_resp = await async_client.post(
        "/api/v1/auth/2fa/setup",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]
    assert secret

    # 3. Verify (Enable)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    verify_resp = await async_client.post(
        "/api/v1/auth/2fa/verify",
        json={"code": code},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["message"] == "2FA enabled successfully"

    # 4. Verify status in /me
    me_resp = await async_client.get(
        "/api/v1/users/me", 
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.json()["is_2fa_enabled"] is True

@pytest.mark.asyncio
async def test_2fa_login_flow(async_client: AsyncClient, db_session: AsyncSession):
    # Manually create user with 2FA enabled
    password = "secret_password"
    hashed_pw = get_password_hash(password)
    secret = pyotp.random_base32()
    user = User(
        login="2fa_user",
        email="2fa@test.com",
        password_hash=hashed_pw,
        role=UserRole.WAREHOUSEMAN,
        is_2fa_enabled=True,
        totp_secret=secret,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    # 1. Login -> Expect Temp Token
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "2fa_user", "password": password}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_2fa_required"] is True
    temp_token = data["access_token"]

    # 2. Access Protected -> Should fail
    resp_prot = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    assert resp_prot.status_code == 401

    # 3. Complete 2FA Login
    totp = pyotp.TOTP(secret)
    code = totp.now()
    resp_2fa = await async_client.post(
        "/api/v1/auth/2fa/login",
        json={"token": temp_token, "code": code}
    )
    assert resp_2fa.status_code == 200
    final_token = resp_2fa.json()["access_token"]
    
    # 4. Access Protected -> Success
    resp_me = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {final_token}"}
    )
    assert resp_me.status_code == 200
