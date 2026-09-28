import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from backend.db.models.user import User
from backend.core.security import hash_password, create_access_token

@pytest.mark.asyncio
async def test_auth_invalid_jwt_rejected(async_client):
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    res = await async_client.get("/auth/me", headers=headers)
    assert res.status_code == 401

@pytest.mark.asyncio
async def test_auth_expired_jwt_rejected(async_client, db_session, monkeypatch):
    from backend.core.config import settings
    # Monkeypatch the token expiry to be very short for this test
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
    
    password = "MySecurePassword123!"
    user = User(email=f"test_{uuid4()}@example.com", password_hash=hash_password(password))
    db_session.add(user)
    await db_session.commit()
    
    token = create_access_token(str(user.id))
    headers = {"Authorization": f"Bearer {token}"}
    
    res = await async_client.get("/auth/me", headers=headers)
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower() or "validate" in res.json()["detail"].lower()

@pytest.mark.asyncio
async def test_password_reset_token_single_use(async_client, db_session):
    email = f"reset_{uuid4()}@example.com"
    user = User(email=email, password_hash=hash_password("oldpassword"))
    db_session.add(user)
    await db_session.commit()
    
    # 1. Request reset
    req_res = await async_client.post("/auth/reset-password/request", json={"email": email})
    assert req_res.status_code == 200
    msg = req_res.json()["message"]
    # Extract dev token
    token = msg.split("[DEV] Token: ")[1].strip() if "[DEV] Token:" in msg else None
    if not token:
        pytest.skip("No dev token returned, cannot test reset flow")
        
    # 2. Confirm reset
    conf_res = await async_client.post("/auth/reset-password/confirm", json={"token": token, "new_password": "NewPassword123!"})
    assert conf_res.status_code == 200
    
    # 3. Attempt to use the same token again (BUG check)
    conf_res_2 = await async_client.post("/auth/reset-password/confirm", json={"token": token, "new_password": "AnotherPassword"})
    # It MUST fail, the token should be single-use (deleted or marked used)
    if conf_res_2.status_code == 200:
        pytest.fail("BUG: Password reset token is not single-use! Reused successfully.")
    assert conf_res_2.status_code in (400, 401, 404, 422)

@pytest.mark.asyncio
async def test_auth_login_workflow(async_client, db_session):
    email = f"user_{uuid4()}@example.com"
    password = "ValidPassword123!"
    
    # Register
    res = await async_client.post("/auth/register", json={"email": email, "password": password, "full_name": "Test User"})
    assert res.status_code == 201
    
    # Login
    login_res = await async_client.post("/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    
    # Check refresh cookie
    cookies = [c for c in login_res.headers.get_list("set-cookie") if "refresh_token" in c]
    assert len(cookies) > 0, "No refresh token cookie set"
    
    # Test me
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me_res = await async_client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email
