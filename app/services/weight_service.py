from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from app.database.models.rack import Rack
from app.core.redis_client import RedisClient
import logging

logger = logging.getLogger("WEIGHT_SERVICE")

class WeightService:
    @staticmethod
    async def calculate_and_cache_weights(db: AsyncSession):
        """
        Calculates weight of products for each slot (rack, row, col) and caches in Redis.
        Key format: rack:{designation}:row:{row}:col:{col}:expected_weight
        """
        logger.info("Starting product weight calculation per slot...")
        

        stmt = (
            select(
                Rack.designation,
                StockItem.position_row,
                StockItem.position_col,
                func.sum(ProductDefinition.weight_kg).label("total_weight")
            )
            .join(ProductDefinition, StockItem.product_id == ProductDefinition.id)
            .join(Rack, StockItem.rack_id == Rack.id)
            .where(StockItem.rack_id.isnot(None))
            .group_by(Rack.designation, StockItem.position_row, StockItem.position_col)
        )

        result = await db.execute(stmt)
        rows = result.all()

        redis_client = RedisClient.get_client()
        
        count = 0
        async with redis_client.pipeline() as pipe:
            for designation, row_pos, col_pos, total_weight in rows:
                if not total_weight:
                    continue
                
                # rack:{designation}:row:{r}:col:{c}:expected_weight
                key = f"rack:{designation}:row:{row_pos}:col:{col_pos}:expected_weight"
                
                await pipe.set(key, float(total_weight))
                count += 1
            
            await pipe.execute()
            
        logger.info(f"Cached weights for {count} slots.")
