from fastapi import APIRouter, Depends
from app.schemas.user import UserIn
from app.core import deps
from app.database.session import get_db
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession

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