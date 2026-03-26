from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.core import deps
from app.database.models.user import User
from app.services.inventory_service import InventoryService

router = APIRouter()

@router.post("/run-inventory")
async def start_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_admin)
):
    """
    Uruchamia proces fizycznej inwentaryzacji przy pomocy drukarki 3D.
    """
    return await InventoryService.run_full_inventory(db, current_user.id)