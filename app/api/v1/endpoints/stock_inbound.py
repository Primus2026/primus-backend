from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.core import deps
from app.schemas.allocation import AllocationRequest
from app.schemas.stock import StockOut
from app.services.allocation_service import AllocationService
from app.services.gcode_service import gcode
from app.database.models.user import User
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select
from datetime import datetime, timedelta

router = APIRouter()

@router.post("/direct-add", response_model=StockOut, status_code=201)
async def direct_add_stock_item(
    payload: AllocationRequest,
    db: AsyncSession = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis)
):
    """
    Przyjęcie do magazynu w jednym kroku.
    Znajduje optymalne miejsce za pomocą AllocationService i używa G-Code do fizycznego odłożenia, a następnie zapisuje do bazy.
    """
    
    # 1. Alokacja
    allocation = await AllocationService.allocate_item(
        db=db,
        barcode=payload.barcode,
        user=user,
        redis_client=redis_client
    )

    # 2. Pobranie definicji produktu do wstawienia do bazy
    stmt = select(ProductDefinition).where(ProductDefinition.barcode == payload.barcode)
    result = await db.execute(stmt)
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # TU TRZEBA TO ODKOMENTOWAC

    try:
        gcode.pick_from_grid(col=1, row=1, level=0)
        gcode.place_on_grid(col=allocation.col, row=allocation.row, level=allocation.y_position)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd komunikacji z drukarką (G-Code): {str(e)}")

    # 4. Zapis do Bazy
    stock_item = StockItem(
        rack_id=allocation.rack_id,
        position_row=allocation.row,
        position_col=allocation.col,
        y_position=allocation.y_position,
        product_id=product.id,
        entry_date=datetime.now(),
        expiry_date=(datetime.now() + timedelta(days=product.expiry_days)).date(),
        received_by_id=user.id
    )
    
    db.add(stock_item)
    await db.commit()
    await db.refresh(stock_item, ["product", "receiver"])
    
    # Update cache weight
    await redis_client.hincrby(f"Rack:{allocation.rack_designation}", "weight_kg", int(product.weight_kg))
    await redis_client.set(f"Weight:{allocation.rack_designation}:{allocation.row}:{allocation.col}", product.weight_kg)
    
    return StockOut(
        id=stock_item.id,
        product=stock_item.product,
        rack_id=stock_item.rack_id,
        position_row=stock_item.position_row,
        position_col=stock_item.position_col,
        y_position=stock_item.y_position,
        entry_date=stock_item.entry_date,
        expiry_date=stock_item.expiry_date,
        received_by=stock_item.receiver
    )