from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import deps
from app.database.session import get_db
from app.database.models.user import User
from app.models.token import Token
from app.services.auth_service import AuthService

router = APIRouter()

@router.post("/login", response_model=Token)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect login or password")
    


    return AuthService.create_login_token(user)

@router.post("/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    return await AuthService.setup_2fa(db, current_user)

@router.post("/2fa/verify")
async def verify_2fa_setup(
    code: str = Body(..., embed=True),
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Verify the code to ENABLE 2FA.
    """
    success = await AuthService.verify_and_enable_2fa(db, current_user, code)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid code")
    
    return {"message": "2FA enabled successfully"}

@router.post("/2fa/login", response_model=Token)
async def login_2fa(
    token: str = Body(...),
    code: str = Body(...),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Complete login with 2FA code using the temp token from /login.
    """
    return await AuthService.login_2fa(db, token, code)

@router.get("/me")
async def read_users_me(
    current_user: User = Depends(deps.get_current_user)
):
    return {"id": current_user.id, "login": current_user.login, "email": current_user.email, "is_2fa_enabled": current_user.is_2fa_enabled}
