from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.core import deps
from app.database.models.user import User
from app.services.inventory_service import InventoryService

router = APIRouter()

@router.post("/run-inventory-start")
async def start_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_admin)
):
    """
    KROK 1: Nadpisuje bazę danych rzeczywistym skanem planszy.
    """
    return await InventoryService.run_full_inventory(db, current_user.id)

@router.post("/run-audit")
async def run_inventory_audit(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_admin)
):
    """
    KROK 2: Tylko porównuje bazę ze stanem faktycznym i zwraca raport błędów.
    """
    return await InventoryService.audit_inventory(db)