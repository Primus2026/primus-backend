from app.schemas.stock import RackLocation, StockOut
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import deps
from app.schemas.allocation import AllocationRequest, AllocationResponse
from app.services.allocation_service import AllocationService
from app.database.models.user import User
from redis.asyncio import Redis

router = APIRouter()

@router.post("", response_model=AllocationResponse, status_code=202)
async def allocate_item(
    payload: AllocationRequest,
    db: AsyncSession = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis)
):
    """
    Inicjalizacja procesu alokacji towaru.
    
    Weryfikuje kod kreskowy, znajduje najlepsze miejsce na regale i rezerwuje je tymczasowo.
    """

    return await AllocationService.allocate_item(
        db=db,
        barcode=payload.barcode,
        user=user,
        redis_client=redis_client
    )

@router.post("/confirm", response_model=StockOut, status_code=201)
async def confirm_allocation(
    payload: RackLocation,
    db: AsyncSession = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis)
):
    """
    Potwierdzenie alokacji (fizyczne odłożenie towaru).
    
    Finalizuje proces, zapisując towar w bazie danych i zwalniając tymczasową rezerwację.
    """
    return await AllocationService.confirm_allocation(
        db=db,
        user=user,
        redis_client=redis_client,
        rack_location=payload
    )

@router.post("/cancel", response_model=AllocationResponse, status_code=201)
async def cancel_allocation(
    payload: RackLocation,
    user: User = Depends(deps.get_current_user), \
    redis_client: Redis = Depends(deps.get_redis)
):
    """
    Anulowanie alokacji.
    
    Zwalnia tymczasową rezerwację miejsca na regale.
    """
    return await AllocationService.cancel_allocation(
        user=user,
        redis_client=redis_client,
        rack_location=payload
    )