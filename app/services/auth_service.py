from datetime import timedelta
from typing import Any
import io
import base64

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
import pyotp
import qrcode
from jose import jwt, JWTError

from app.core import security
from app.core.config import settings
from app.database.models.user import User
from app.models.token import Token

class AuthService:
    @staticmethod
    async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
        result = await db.execute(select(User).where(User.login == username))
        user = result.scalars().first()
        if not user or not security.verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    def create_login_token(user: User) -> Token:
        if user.is_2fa_enabled:
             # Generate temp token
            access_token_expires = timedelta(minutes=5)
            access_token = security.create_access_token(
                user.id, expires_delta=access_token_expires, claims={"2fa_required": True}
            )
            return Token(access_token=access_token, token_type="bearer", is_2fa_required=True)
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        return Token(access_token=access_token, token_type="bearer", is_2fa_required=False)

    @staticmethod
    async def setup_2fa(db: AsyncSession, user: User) -> dict[str, str]:
        secret = pyotp.random_base32()
        user.totp_secret = secret
        db.add(user)
        await db.commit()
        await db.refresh(user)

        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Primus 2026")
        
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        return {
            "secret": secret,
            "qr_code_url": uri,
            "qr_code_image": f"data:image/png;base64,{img_str}"
        }

    @staticmethod
    async def verify_and_enable_2fa(db: AsyncSession, user: User, code: str) -> bool:
        if not user.totp_secret:
            raise HTTPException(status_code=400, detail="2FA setup not initiated")
        
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code):
            return False
            
        user.is_2fa_enabled = True
        db.add(user)
        await db.commit()
        return True

    @staticmethod
    async def login_2fa(db: AsyncSession, token: str, code: str) -> Token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: str = payload.get("sub")
        except JWTError:
             raise HTTPException(status_code=401, detail="Invalid token")

        try:
            u_id = int(user_id)
        except (ValueError, TypeError):
             raise HTTPException(status_code=401, detail="Invalid token")

        result = await db.execute(select(User).where(User.id == u_id))
        user = result.scalars().first()
        
        if not user:
             raise HTTPException(status_code=401, detail="User not found")

        if not user.is_2fa_enabled or not user.totp_secret:
             raise HTTPException(status_code=400, detail="2FA not enabled for user")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code):
             raise HTTPException(status_code=400, detail="Invalid code")
             
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_token = security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        return Token(access_token=new_token, token_type="bearer", is_2fa_required=False)
