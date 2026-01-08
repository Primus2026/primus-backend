import pytest
from httpx import AsyncClient
from app.core.security import get_password_hash
import pyotp
from app.database.models.user import User, UserRole

@pytest.mark.asyncio
async def test_auth_workflow(async_client: AsyncClient, db_session):
    # 1. Create User
    password = "secret_password"
    hashed_pw = get_password_hash(password)
    user = User(
        login="testauth",
        email="auth@test.com",
        password_hash=hashed_pw,
        role=UserRole.WAREHOUSEMAN,
        is_2fa_enabled=False
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. Login (No 2FA)
    print("Step 2: Login")
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "testauth", "password": password}
    )
    assert response.status_code == 200, f"Login failed: {response.status_code} {response.text}"
    data = response.json()
    assert "access_token" in data
    assert data["is_2fa_required"] is False
    token = data["access_token"]

    # 3. Access Protected Route
    print("Step 3: Access Protected")
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Access me failed: {resp.status_code} {resp.text}"
    assert resp.json()["login"] == "testauth"
    assert resp.json()["is_2fa_enabled"] is False

    # 4. Setup 2FA
    print("Step 4: Setup 2FA")
    resp = await async_client.post(
        "/api/v1/auth/2fa/setup",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Setup 2FA failed: {resp.status_code} {resp.text}"
    setup_data = resp.json()
    secret = setup_data["secret"]
    assert secret

    # 5. Enable 2FA
    print("Step 5: Enable 2FA")
    totp = pyotp.TOTP(secret)
    code = totp.now()
    resp = await async_client.post(
        "/api/v1/auth/2fa/verify",
        json={"code": code},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Enable 2FA (Verify) failed: {resp.status_code} {resp.text}"
    assert resp.json()["message"] == "2FA enabled successfully"

    # 6. Login (With 2FA enabled)
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "testauth", "password": password}
    )
    assert response.status_code == 200
    data = response.json()
    temp_token = data["access_token"]
    assert data["is_2fa_required"] is True

    # 7. Try to access Protected Route with Temp Token -> Should Fail 401
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    assert resp.status_code == 401

    # 8. Complete 2FA Login
    code = totp.now()
    resp = await async_client.post(
        "/api/v1/auth/2fa/login",
        json={"token": temp_token, "code": code}
    )
    assert resp.status_code == 200, f"2FA Login failed: {resp.status_code} {resp.text}"
    final_data = resp.json()
    final_token = final_data["access_token"]
    assert final_data["is_2fa_required"] is False

    # 9. Access Protected Route with Final Token
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {final_token}"}
    )
    assert resp.status_code == 200, f"Final Me failed: {resp.status_code} {resp.text}"
    assert resp.json()["is_2fa_enabled"] is True
