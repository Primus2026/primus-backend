from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.product_stats import ProductStats
from app.database.models.product_definition import ProductDefinition, FrequencyClass
from sqlalchemy import select
from redis.asyncio import Redis
from app.core.config import settings
import math

class ProductStatsService:
    @staticmethod
    async def update_product_stats(db: AsyncSession, product_id: int, count: int, redis_client: Redis):
        # 1. Update individual product stats
        stmt = select(ProductStats).where(ProductStats.product_id == product_id)
        result = await db.execute(stmt)
        product_stats = result.scalars().first()
        
        if not product_stats:
            product_stats = ProductStats(
                product_id=product_id, 
                pick_count=count, 
                total_since_last_update=count
            )
            db.add(product_stats)
        else:
            product_stats.pick_count += count
            product_stats.total_since_last_update += count
        
        await db.commit()
        await db.refresh(product_stats)

        # 2. Update Global Counter in Redis
        global_counter_key = "global_transaction_counter"
        current_count = await redis_client.incrby(global_counter_key, count)
        
        # 3. Check trigger condition (every 10th transaction)
        if current_count % 10 == 0:
            # Trigger frequency recalculation
            from app.tasks.product_stats_tasks import update_frequencies_task
            update_frequencies_task.delay()
    
    @staticmethod 
    async def update_products_frequencies(db: AsyncSession):
        # Fetch stats JOIN ProductDefinition
        stmt = select(ProductStats, ProductDefinition).join(ProductDefinition).order_by(ProductStats.pick_count.desc())
        results = await db.execute(stmt)
        # results contains list of (ProductStats, ProductDefinition) tuples
        rows = results.all()

        total = len(rows)
        if total == 0:
            return

        # ABC Analysis: A=Top 30%, B=Next 40%, C=Bottom 30%
        # Calculate indices with ceiling to ensure at least one 'A' for small sets
        a_limit = math.ceil(total * 0.30)
        b_limit = math.ceil(total * 0.70) # Top 30 + 40 = 70%

        for i, (stat, product) in enumerate(rows):
            if i < a_limit:
                product.frequency_class = FrequencyClass.A
            elif i < b_limit:
                product.frequency_class = FrequencyClass.B
            else:
                product.frequency_class = FrequencyClass.C
            db.add(product) # Ensure tracked
        
        await db.commit()