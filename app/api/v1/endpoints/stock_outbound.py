from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.stock import RackLocation, RackLocationManual
from app.services.stock_service import StockService
from redis.asyncio import Redis
from app.core import deps
from app.database.session import get_db
from app.database.models.user import User
from app.schemas.msg import Msg

router = APIRouter()


@router.post("/initiate/{barcode}", responses={
    404: {"description": "Stock item not found"},
}, response_model=RackLocation)
async def outbound_stock_item_initiate( 
    barcode: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis), 
):
    """ 
    Initiate the outbound process for a stock item

    **barcode**:
    Barcode of the product to be removed

    Returns the location for the item to be removed (compliant with FIFO)
    This can be followed by a post call to /confirm
    
    """
    return await StockService.outbound_stock_item_initiate(barcode, user, redis_client, db)
    
@router.post("/confirm", responses={
    404: {"description": "Stock item not found"},
    403: {"description": "You are not authorized to confirm this outbound process"},
}, response_model=Msg)
async def outbound_stock_item_confirm(
    rack_location: RackLocation,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis),
):
    """
    Confirm the outbound process for a stock item

    **rack_location**:
    Location of the item to be removed

    Returns a message indicating success
    """

    return await StockService.outbound_stock_item_confirm(rack_location, user, redis_client, db)
        

@router.post("/cancel", response_model=Msg)
async def outbound_stock_item_cancel(
    rack_location: RackLocation,
    user: User = Depends(deps.get_current_user),
    redis_client: Redis = Depends(deps.get_redis),
):
    """
    Cancel the outbound process for a stock item

    **rack_location**:
    Location of the item to be removed

    Returns a message indicating success
    """

    return await StockService.outbound_stock_item_cancel(rack_location, user, redis_client)

@router.post("/manual", response_model=Msg)
async def outbound_stock_item_manual(
    rack_location: RackLocationManual,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(deps.get_current_admin),
    redis_client: Redis = Depends(deps.get_redis),
):
    """
    Manually confirm the outbound process for a stock item

    **rack_location**:
    Location of the item to be removed

    Returns a message indicating success
    """

    return await StockService.outbound_stock_item_manual(rack_location, db, redis_client)