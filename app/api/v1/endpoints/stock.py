from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import deps
from app.schemas.stock import ProductStockGroup
from app.services.stock_service import StockService
from app.database.models.user import User

router = APIRouter()

@router.get("/", response_model=List[ProductStockGroup])
async def get_grouped_stocks(
    db: AsyncSession = Depends(deps.get_db),
    admin: User = Depends(deps.get_current_admin), 
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, le=100, description="Items per page"),
    name: Optional[str] = Query(None, description="Filter by product name")
):
    skip = (page - 1) * limit
    return await StockService.get_grouped_stocks(
        db=db,
        skip=skip,
        limit=limit,
        product_name=name
    )