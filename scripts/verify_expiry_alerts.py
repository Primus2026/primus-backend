from datetime import datetime, timedelta
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete
from app.database.models import User, UserRole, ProductDefinition, StockItem, Rack, Alert, AlertType
from app.core import security
from app.core.config import settings
from app.tasks.report_tasks import _process_expiry_report_async
import os
import sys

# Setup DB connection
engine = create_async_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def setup_data(db: AsyncSession):
    # 1. Ensure Rack exists
    rack = await db.get(Rack, 1)
    if not rack:
        rack = Rack(
            id=1,
            designation="TEST-RACK", 
            rows_m=5, cols_n=5, 
            temp_min=0, temp_max=10, 
            max_weight_kg=100, max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100
        )
        db.add(rack)
        await db.commit()
    
    # We must refresh rack to ensure it's bound and attributes are available if we access them
    # OR simpler: just use the ID we know
    rack_id = rack.id
    
    # 2. Create Product
    result = await db.execute(select(ProductDefinition).where(ProductDefinition.barcode == "EXP-12345"))
    product = result.scalars().first()
    
    if not product:
        product = ProductDefinition(
            name="Expiring Product",
            barcode="EXP-12345",
            req_temp_min=0, req_temp_max=5, weight_kg=1,
            dims_x_mm=10, dims_y_mm=10, dims_z_mm=10, expiry_days=1
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
    
    product_id = product.id

    # 3. Create Stock Item expiring in 1 hour
    expiry = datetime.now() + timedelta(hours=1)
    # Ensure receiver exists
    user = (await db.execute(select(User))).scalars().first()
    if not user:
        print("No users in DB, creating mock user")
        user = User(login="mock", password_hash="hash", role=UserRole.WAREHOUSEMAN)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    user_id = user.id

    # Cleanup existing stock item at this position if any
    await db.execute(delete(StockItem).where(
        StockItem.rack_id == rack_id,
        StockItem.position_row == 1,
        StockItem.position_col == 1
    ))
    await db.commit()

    stock_item = StockItem(
        product_id=product_id,
        rack_id=rack_id,
        position_row=1, position_col=1,
        expiry_date=expiry,
        received_by_id=user_id
    )
    db.add(stock_item)
    await db.commit()
    
    return product, stock_item

async def verify():
    async with SessionLocal() as db:
        print("Setting up test data...")
        product, stock_item = await setup_data(db)
        
        print("Running expiry report task...")
        # Call valid async function directly
        result = await _process_expiry_report_async("TEST_TASK_ID")
        print(f"Task result: {result}")
        
        # Verify Alert
        print("Verifying Alert creation...")
        await db.refresh(product)
        stmt = select(Alert).where(
            Alert.product_id == product.id,
            Alert.alert_type == AlertType.EXPIRY_WARNING
        )
        alert_res = await db.execute(stmt)
        alert = alert_res.scalars().first()
        
        if alert:
            print("SUCCESS: Alert created!")
            print(f"Message: {alert.message}")
        else:
            print("FAILURE: Alert NOT created.")
            sys.exit(1)
            
        # Cleanup
        print("Cleaning up...")
        await db.delete(stock_item)
        await db.delete(product)
        if alert:
             await db.delete(alert)
        await db.commit()

if __name__ == "__main__":
    # Ensure PYTHONPATH includes backend root
    current_dir = os.getcwd()
    if current_dir not in sys.path:
        sys.path.append(current_dir)
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(verify())
