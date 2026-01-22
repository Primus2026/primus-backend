from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.stock import RackLocation
from app.database.models.stock_item import StockItem
from app.database.models.user import User
from app.schemas.msg import Msg
from app.database.models.product_definition import ProductDefinition
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app.database.session import get_db
from app.core.config import settings
from sqlalchemy.orm import selectinload
from app.database.models.rack import Rack
import logging

logger = logging.getLogger("STOCK_SERVICE")

class StockService:
    
    @staticmethod
    async def outbound_stock_item_initiate(barcode: str, user: User, redis_client: Redis, db: AsyncSession):

        # Use selectinload to load the rack in async
        stmt = select(StockItem).options(selectinload(StockItem.rack)).where(ProductDefinition.barcode == barcode).join(ProductDefinition).order_by(StockItem.expiry_date.asc()).limit(1)
        result = await db.execute(stmt)
        itemToRemove = result.scalars().first()

        if not itemToRemove:
            raise HTTPException(status_code=404, detail="Stock item not found")

        #Set the expected change flag with format key ${rack_id}:${row}:${col} value ${user_id} 
        key = f"ExpectedChange:{itemToRemove.rack.designation}:{itemToRemove.position_row}:{itemToRemove.position_col}"
        logger.info(f"Initiating outbound. User ID: {user.id} ({type(user.id)}). Key: {key}, Value: {user.id}")
        await redis_client.set(key, user.id, ex=settings.EXPECTED_CHANGE_TTL)

        return RackLocation(designation=itemToRemove.rack.designation, row=itemToRemove.position_row, col=itemToRemove.position_col)
        
    @staticmethod
    async def outbound_stock_item_confirm(rack_location: RackLocation, user: User, redis_client: Redis, db: AsyncSession ):

        expectedChange = await redis_client.get(f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}")

        if not expectedChange:
            raise HTTPException(status_code=404, detail="No expected change found for this rack location, please initiate the outbound process first")

        #The cached value is the issuers user_id
        logger.info(f"Confirming outbound. User ID: {user.id} ({type(user.id)}). Stored ID: {expectedChange} ({type(expectedChange)})")
        if str(expectedChange) != str(user.id):
            logger.error(f"Authorization failed. Stored: {expectedChange}, Current: {user.id}")
            raise HTTPException(status_code=403, detail="You are not authorized to confirm this outbound process")

        stmt = select(StockItem).join(Rack).where(Rack.designation == rack_location.designation, StockItem.position_row == rack_location.row, StockItem.position_col == rack_location.col)
        result = await db.execute(stmt)
        item = result.scalars().first()
        
        if item:
            await db.delete(item)
            await db.commit()
        
        #Remove the cached weight (equal to 0 for the mqtt listiner)
        await redis_client.delete(f"Weight:{rack_location.designation}:{rack_location.row}:{rack_location.col}")

        await redis_client.delete(f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}")

        return Msg(message="Stock item removed successfully")
        
    @staticmethod
    async def outbound_stock_item_cancel(rack_location: RackLocation, user: User, redis_client: Redis):
        expectedChange = await redis_client.get(f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}")

        if not expectedChange:
            raise HTTPException(status_code=404, detail="No expected change found for this rack location, please initiate the outbound process first")

        #the cached value is the issuers user_id
        if str(expectedChange) != str(user.id):
            raise HTTPException(status_code=403, detail="You are not authorized to cancel this outbound process")

        await redis_client.delete(f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}")

        return Msg(message="Stock item outbound process cancelled successfully")
            

        
