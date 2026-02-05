from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.schemas.stock import RackLocation, RackLocationManual, ProductStockGroup
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
from app.database.models.rack import Rack
import logging
import json
from app.services.product_stats_service import ProductStatsService

logger = logging.getLogger("STOCK_SERVICE")


class StockService:

    @staticmethod
    async def outbound_stock_item_initiate(
        barcode: str, user: User, redis_client: Redis, db: AsyncSession
    ):

        # Use selectinload to load the rack in async
        stmt = (
            select(StockItem)
            .options(selectinload(StockItem.rack))
            .where(ProductDefinition.barcode == barcode)
            .join(ProductDefinition)
            .order_by(StockItem.entry_date.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        itemToRemove = result.scalars().first()

        if not itemToRemove:
            raise HTTPException(status_code=404, detail="Produkt nie został znaleziony")

        # Set the expected change flag with format key ${rack_id}:${row}:${col} value ${user_id}
        key = f"ExpectedChange:{itemToRemove.rack.designation}:{itemToRemove.position_row}:{itemToRemove.position_col}"
        
        lock_value = json.dumps({
            "user_id": user.id,
            "type": "OUTBOUND",
            "expected_weight": 0.0
        })

        logger.info(
            f"Initiating outbound. User ID: {user.id} ({type(user.id)}). Key: {key}, Value: {lock_value}"
        )
        await redis_client.set(key, lock_value, ex=settings.EXPECTED_CHANGE_TTL)

        return RackLocation(
            designation=itemToRemove.rack.designation,
            row=itemToRemove.position_row,
            col=itemToRemove.position_col,
        )

    @staticmethod
    async def outbound_stock_item_confirm(
        rack_location: RackLocation, user: User, redis_client: Redis, db: AsyncSession
    ):

        expectedChange = await redis_client.get(
            f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}"
        )

        if not expectedChange:
            raise HTTPException(
                status_code=404,
                detail="Nie znaleziono oczekiwanej zmiany dla tej lokalizacji, proszę zainicjować proces najpierw",
            )

        # The cached value is the issuers user_id
        try:
            change_data = json.loads(expectedChange)
            cached_user_id = change_data.get("user_id")
        except (json.JSONDecodeError, TypeError):
             # Fallback for legacy keys
            cached_user_id = expectedChange.decode("utf-8") if isinstance(expectedChange, bytes) else expectedChange

        logger.info(
            f"Confirming outbound. User ID: {user.id} ({type(user.id)}). Stored ID: {cached_user_id} ({type(cached_user_id)})"
        )
        if str(cached_user_id) != str(user.id):
            logger.error(
                f"Authorization failed. Stored: {cached_user_id}, Current: {user.id}"
            )
            raise HTTPException(
                status_code=403,
                detail="Nie jesteś upoważniony do potwierdzenia tego procesu",
            )

        stmt = (
            select(StockItem)
            .join(Rack)
            .where(
                Rack.designation == rack_location.designation,
                StockItem.position_row == rack_location.row,
                StockItem.position_col == rack_location.col,
            )
        )
        result = await db.execute(stmt)
        item = result.scalars().first()

        if item:
            await db.delete(item)
            await db.commit()
            
            # Update product stats
            await ProductStatsService.update_product_stats(db, item.product_id, 1, redis_client)

        # Remove the cached weight (equal to 0 for the mqtt listiner)
        await redis_client.delete(
            f"Weight:{rack_location.designation}:{rack_location.row}:{rack_location.col}"
        )

        await redis_client.delete(
            f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}"
        )

        return Msg(message="Stock item removed successfully")

    @staticmethod
    async def outbound_stock_item_cancel(
        rack_location: RackLocation, user: User, redis_client: Redis
    ):
        expectedChange = await redis_client.get(
            f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}"
        )

        if not expectedChange:
            raise HTTPException(
                status_code=404,
                detail="Nie znaleziono oczekiwanej zmiany dla tej lokalizacji, proszę zainicjować proces najpierw",
            )

        # the cached value is the issuers user_id
        try:
            change_data = json.loads(expectedChange)
            cached_user_id = change_data.get("user_id")
        except (json.JSONDecodeError, TypeError):
            cached_user_id = expectedChange.decode("utf-8") if isinstance(expectedChange, bytes) else expectedChange

        if str(cached_user_id) != str(user.id):
            raise HTTPException(
                status_code=403,
                detail="Nie jesteś upoważniony do anulowania tego procesu",
            )

        await redis_client.delete(
            f"ExpectedChange:{rack_location.designation}:{rack_location.row}:{rack_location.col}"
        )

        return Msg(message="Stock item outbound process cancelled successfully")

    @staticmethod
    async def get_grouped_stocks(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        product_name: str | None = None
    ) -> list[ProductStockGroup]:
        # Step 1: Get products
        stmt = select(ProductDefinition)
        if product_name:
            stmt = stmt.where(ProductDefinition.name.ilike(f"%{product_name}%"))
        
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        products = result.scalars().all()
        
        if not products:
            return []
            
        product_ids = [p.id for p in products]
        
        # Step 2: Get stock items for these products and load receiver and rack
        items_stmt = (
            select(StockItem)
            .where(StockItem.product_id.in_(product_ids))
            .options(selectinload(StockItem.receiver), selectinload(StockItem.rack))
            .order_by(StockItem.expiry_date)
        )
        
        items_result = await db.execute(items_stmt)
        all_items = items_result.scalars().all()
        
        # Step 3: Group them
        items_by_product = {p_id: [] for p_id in product_ids}
        for item in all_items:
            # Map item to StockItemSimpleOut schema format
            # Use 'receiver' relationship for 'received_by' field
            # We construct the dict or let Pydantic handle if we pass object + extra
            # Since StockItemSimpleOut expects 'received_by' but model has 'receiver',
            # we might need to rely on Pydantic's from_attributes (orm_mode) and aliasing 
            # OR just construct objects manually to be safe.
            # However, since schemas usually use from_attributes=True in this project (likely), 
            # let's assume standard usage. But to match `received_by` field with `receiver` relationship:
            # If StockItemSimpleOut doesn't have an alias, we need to provide `received_by`.
            
            # Helper to convert to dict and map receiver
            item_dict = {
                "id": item.id,
                "rack_id": item.rack_id,
                "position_row": item.position_row,
                "position_col": item.position_col,
                "entry_date": item.entry_date,
                "expiry_date": item.expiry_date.date() if isinstance(item.expiry_date, datetime) else item.expiry_date,
                "received_by": {"id": item.receiver.id, "email": item.receiver.email},
                "rack": item.rack
            }
            items_by_product[item.product_id].append(item_dict)
            
        # Step 4: Construct result
        results = []
        for product in products:
            results.append({
                "product": product,
                "stock_items": items_by_product[product.id]
            })
            
        return results

    @staticmethod
    async def outbound_stock_item_manual(rack_location: RackLocationManual, db: AsyncSession, redis_client: Redis):
        rack = await db.execute(
            select(Rack)
            .where(
                Rack.id == rack_location.rack_id,
            )
        )
        rack = rack.scalars().first()
        if not rack:
            raise HTTPException(
                status_code=404,
                detail="Regał nie został znaleziony",
            )
        
        stock_item = await db.execute(
            select(StockItem)
            .where(
                StockItem.rack_id == rack.id,
                StockItem.position_row == rack_location.row,
                StockItem.position_col == rack_location.col,
            )
        )
        stock_item = stock_item.scalars().first()
        if not stock_item:
            raise HTTPException(
                status_code=404,
                detail="Produkt nie został znaleziony",
            )   
        
        await db.delete(stock_item)
        await db.commit()
        
        # Update product stats
        await ProductStatsService.update_product_stats(db, stock_item.product_id, 1, redis_client)
        
        return Msg(message="Produkt został usunięty pomyślnie")        