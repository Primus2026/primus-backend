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
                detail="User does not exist"
            )
        if existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already active"
            )
        
        existing_user.is_active = True 

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error while deleting user"
            )
            
        return {"message": "User activated successfully"} 
    
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
                detail="User does not exist"
            )
        if existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already active"
            )
        
        await db.delete(existing_user)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error while deleting user"
            )
            
        return {"message": "User deleted successfully"}
        
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