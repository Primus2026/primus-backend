from fastapi import APIRouter, Depends
from app.schemas.user import UserIn
from app.core import deps
from app.database.session import get_db
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User

router = APIRouter()

@router.post("/request_register")
async def request_register(
    user: UserIn,
    db: AsyncSession = Depends(get_db)
):
    return await UserService.request_registration(
        db=db,
        user_in=user
    )
    
@router.post("/create_admin")
async def create_admin(
    db: AsyncSession = Depends(get_db)
):
    return await UserService.create_admin(db)


@router.put("/approve_user/{user_id}")
async def approve_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User =  Depends(deps.get_current_admin)
):
    return await UserService.approve_user(
        db=db,
        user_id=user_id
    )
@router.put("/reject_user/{user_id}")
async def reject_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User =  Depends(deps.get_current_admin)
):
    return await UserService.reject_user(
        db=db,
        user_id=user_id
    )