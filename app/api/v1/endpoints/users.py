from fastapi import APIRouter, Depends
from app.schemas.user import UserIn, UserOut
from app.schemas.msg import Msg
from app.core import deps
from app.database.session import get_db
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User
from typing import List
router = APIRouter()


@router.post(
    "/request_register",
    status_code=201,
    summary="Register new user",
    response_model=UserOut,
    responses={
        409: {"description": "User with this login already exists"},
        500: {"description": "Internal Server Error"},
    },
)
async def request_register(user: UserIn, db: AsyncSession = Depends(get_db)):
    """
    Register a new user request.

    This endpoint handles the initial registration of a user. The user is created with
    `is_active=False` and requires administrator approval.
    """
    return await UserService.request_registration(db=db, user_in=user)


@router.post(
    "/create_admin",
    summary="Create default admin",
    response_model=UserOut | None,
    responses={500: {"description": "Internal Server Error"}},
)
async def create_admin(db: AsyncSession = Depends(get_db)):
    """
    Create a default administrator account.

    This is a utility endpoint to seed an admin user if one does not already exist
    based on the `ADMIN_LOGIN` setting.
    """
    return await UserService.create_admin(db)


@router.put(
    "/approve_user/{user_id}",
    summary="Approve user registration",
    response_model=Msg,
    responses={
        404: {"description": "User not found"},
        400: {"description": "User already active"},
        500: {"description": "Internal Server Error"},
    },
)
async def approve_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(deps.get_current_admin),
):
    """
    Approve a pending user registration.

    Activates a user account (`is_active=True`) that was previously created via registration.
    Only accessible by administrators.
    """
    return await UserService.approve_user(db=db, user_id=user_id)


@router.put(
    "/reject_user/{user_id}",
    summary="Reject user registration",
    response_model=Msg,
    responses={
        404: {"description": "User not found"},
        400: {"description": "User already active"},
        500: {"description": "Internal Server Error"},
    },
)
async def reject_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(deps.get_current_admin),
):
    """
    Reject a pending user registration.

    Permanently deletes a user account that is pending approval.
    Only accessible by administrators.
    """
    return await UserService.reject_user(db=db, user_id=user_id)


@router.get("/me", summary="Get current user", response_model=UserOut)
async def get_me(
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get current user details.

    Retrieves the information of the currently authenticated user.
    """
    return {
        "id": current_user.id,
        "login": current_user.login,
        "email": current_user.email,
        "role": current_user.role,
        "is_2fa_enabled": current_user.is_2fa_enabled,
        "is_active": current_user.is_active,
    }

@router.get("/warehouse_workers", summary="Gets all warehouse workers",
             response_model=List[UserOut]
             )
async def get_all_warehouse_workers(
    current_admin: User = Depends(deps.get_current_admin),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    """
    return await UserService.get_all_warehouse_workers(db)

@router.get("/requests", summary="Gets all users signup requests"
            , response_model=List[UserOut]
            )
async def get_all_warehouse_workers(
    current_admin: User = Depends(deps.get_current_admin),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    """
    return await UserService.get_not_active_users(db)


@router.delete(
    "/{user_id}",
    summary="Delete a user",
    response_model=Msg,
    responses={
        403: {"description": "Cannot delete an administrator"},
        404: {"description": "User not found"},
        500: {"description": "Internal Server Error"},
    },
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_admin: User = Depends(deps.get_current_admin),
):
    """
    Delete a user account.

    Removes a user from the system. Cannot be used to delete administrators.
    Only accessible by administrators.
    """
    return await UserService.delete_user(db=db, user_id=user_id)