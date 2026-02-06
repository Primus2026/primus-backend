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
    summary="Rejestracja nowego użytkownika",
    response_model=UserOut,
    responses={
        409: {"description": "Użytkownik o takim loginie już istnieje"},
        500: {"description": "Błąd serwera"},
    },
)
async def request_register(user: UserIn, db: AsyncSession = Depends(get_db)):
    """
    Rejestracja wniosku o nowe konto.
    
    Tworzy użytkownika ze statusem `is_active=False`. Wymaga akceptacji administratora.
    """
    return await UserService.request_registration(db=db, user_in=user)


@router.post(
    "/create_admin",
    summary="Utworzenie domyślnego administratora",
    response_model=UserOut | None,
    responses={500: {"description": "Błąd serwera"}},
)
async def create_admin(db: AsyncSession = Depends(get_db)):
    """
    Utworzenie domyślnego konta administratora.
    
    Pomocniczy endpoint do inicjalizacji konta admina, jeśli nie istnieje.
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
    Zatwierdzenie oczekującej rejestracji.
    
    Aktywuje konto użytkownika (`is_active=True`). Dostępne tylko dla administratorów.
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
    Odrzucenie oczekującej rejestracji.
    
    Trwale usuwa konto oczekujące na akceptację. Dostępne tylko dla administratorów.
    """
    return await UserService.reject_user(db=db, user_id=user_id)


@router.get("/me", summary="Pobranie danych obecnego użytkownika", response_model=UserOut)
async def get_me(
    current_user: User = Depends(deps.get_current_user),
):
    """
    Zwraca szczegóły zalogowanego użytkownika.
    
    Pobiera informacje o aktualnie uwierzytelnionym użytkowniku.
    """
    return {
        "id": current_user.id,
        "login": current_user.login,
        "email": current_user.email,
        "role": current_user.role,
        "is_2fa_enabled": current_user.is_2fa_enabled,
        "is_active": current_user.is_active,
    }

@router.get("/warehouse_workers", summary="Pobranie listy magazynierów",
             response_model=List[UserOut]
             )
async def get_all_warehouse_workers(
    current_admin: User = Depends(deps.get_current_admin),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    """
    return await UserService.get_all_warehouse_workers(db)

@router.get("/requests", summary="Pobranie wniosków o rejestrację"
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
    Usunięcie konta użytkownika.
    
    Dostępne tylko dla administratorów. Nie można usunąć konta administratora.
    """
    return await UserService.delete_user(db=db, user_id=user_id)