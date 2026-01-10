from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.user import User, UserRole
from app.schemas.user import UserIn
from app.core import security # Zakładam, że tu masz funkcje do hashowania
from app.core.config import settings

class UserService:
    @staticmethod 
    async def request_registration(db: AsyncSession, user_in: UserIn) -> User:
        result = await db.execute(select(User).where(User.login == user_in.login))
        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this login already exists"
            )

        new_user = User(
            login=user_in.login,
            email=user_in.email,
            password_hash=security.get_password_hash(user_in.password),
            is_2fa_enabled=False,
            is_active=False,
            role=UserRole.WAREHOUSEMAN
        )

        db.add(new_user)
        try:
            await db.commit()
            await db.refresh(new_user)
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error"
            )

        return new_user
    
    @staticmethod
    async def create_admin(db: AsyncSession):
        result = await db.execute(select(User).where(User.login == settings.ADMIN_LOGIN))
        existing_admin = result.scalars().first()

        if existing_admin:
            return
        # temporary function for generating admin

        new_user = User(
            login=settings.ADMIN_LOGIN,
            email="admin@admin.pl",
            password_hash=security.get_password_hash(settings.ADMIN_PASSWORD),
            is_2fa_enabled=False,
            is_active=True,
            role=UserRole.ADMIN
        )
        db.add(new_user)
        try:
            await db.commit()
            await db.refresh(new_user)
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error during creating admin"
            )

        return new_user