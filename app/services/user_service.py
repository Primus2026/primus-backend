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
                detail="Użytkownik z tym loginem już istnieje"
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
                detail="Nieoczekiwany błąd"
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
                detail="Błąd podczas tworzenia administratora"
            )

        return new_user
    
    @staticmethod
    async def approve_user(db: AsyncSession, user_id: int):
        result = await db.execute(
            select(User).where(
                User.id == user_id
            )
        )
        existing_user = result.scalars().first()
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Użytkownik nie istnieje"
            )
        if existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Użytkownik jest już aktywny"
            )
        
        existing_user.is_active = True 

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Błąd podczas aktywacji użytkownika"
            )
            
        return {"message": "Użytkownik aktywowany pomyślnie"} 
    
    @staticmethod
    async def reject_user(db: AsyncSession, user_id: int):
        result = await db.execute(
            select(User).where(
                User.id == user_id
            )
        )
        existing_user = result.scalars().first()
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Użytkownik nie istnieje"
            )
        if existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Użytkownik jest już aktywny"
            )
        
        await db.delete(existing_user)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Błąd podczas odrzucania użytkownika"
            )
            
        return {"message": "Użytkownik został odrzucony"}
        
    @staticmethod 
    async def get_all_warehouse_workers(db: AsyncSession):
        result = await db.execute(
            select(User).where(
                User.is_active == True,
                User.role == UserRole.WAREHOUSEMAN
            )
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_not_active_users(db: AsyncSession):
        result =  await db.execute(
            select(User).where(
                User.is_active == False,
                User.role == UserRole.WAREHOUSEMAN 
            )
        )
        return result.scalars().all()

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: int):
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Użytkownik nie istnieje"
            )

        if user.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nie można usunąć administratora"
            )

        await db.delete(user)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Błąd podczas usuwania użytkownika"
            )
        return {"message": "Użytkownik usunięty pomyślnie"}