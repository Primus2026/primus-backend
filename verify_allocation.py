
import asyncio
import json
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Mocking app dependencies before importing service
import sys
sys.modules['app.core.config'] = MagicMock()
sys.modules['app.core.config'].settings.EXPECTED_CHANGE_TTL = 300

from app.schemas.stock import RackLocation
from app.database.models.product_definition import ProductDefinition, FrequencyClass
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.user import User
from app.services.allocation_service import AllocationService

async def main():
    print("Starting verification...")

    # Mocks
    db = AsyncMock()
    redis = AsyncMock()
    user = User(id=1, email="test@example.com")
    
    # Setup Data
    product = ProductDefinition(
        id=101, 
        barcode="12345", 
        name="Test Product", 
        req_temp_min=0, 
        req_temp_max=10, 
        dims_x_mm=10, dims_y_mm=10, dims_z_mm=10,
        weight_kg=5.0,
        frequency_class=FrequencyClass.A,
        expiry_days=30 # 30 days expiry
    )
    
    rack = Rack(
        id=1, 
        designation="RACK-A", 
        temp_min=0, temp_max=10, 
        max_dims_x_mm=100, max_dims_y_mm=100, max_dims_z_mm=100,
        max_weight_kg=1000,
        rows_m=1, cols_n=1,
        distance_from_exit_m=10
    )

    # Mock DB Executions
    
    # Create a mock result object that returns scalars
    def mock_execute_side_effect(*args, **kwargs):
        stmt = str(args[0])
        print(f"DEBUG SQL: {stmt}")
        result = MagicMock()
        
        # Simplified Mock Strategy: Always return valid data based on table content
        if "product_definitions" in stmt:
             result.scalars.return_value.first.return_value = product
             result.scalar_one_or_none.return_value = product
             result.scalars.return_value.all.return_value = [product]
             
        elif "racks" in stmt:
            result.scalars.return_value.all.return_value = [rack]
            result.scalars.return_value.first.return_value = rack
            result.scalar_one_or_none.return_value = rack
            
        elif "stock_items" in stmt: 
            result.fetchall.return_value = [] # No slots occupied
            
        else:
            result.scalars.return_value.first.return_value = None
            
        return result

    db.execute.side_effect = mock_execute_side_effect
    
    # Mock Redis Exists (No locks)
    redis.exists.return_value = False
    
    # --- TEST ALLOCATION ---
    print("\n--- Testing allocate_item ---")
    resp = await AllocationService.allocate_item(db, "12345", user, redis)
    print(f"Allocation Response: {resp}")
    
    # Verify Redis Set
    call_args = redis.set.call_args
    if call_args:
        key, value = call_args[0]
        print(f"Redis Set Key: {key}")
        print(f"Redis Set Value: {value}")
        data = json.loads(value)
        assert data['user_id'] == user.id
        assert data['product_id'] == product.id
        print("✅ Redis currently stores product_id correctly!")
    else:
        print("❌ Redis set was not called!")
        return

    # --- TEST CONFIRMATION ---
    print("\n--- Testing confirm_allocation ---")
    
    # Setup mocks for confirmation
    # Redis get returns the value we just verified
    redis.get.return_value = json.dumps({"user_id": user.id, "product_id": product.id})
    
    payload = RackLocation(designation="RACK-A", row=1, col=1)
    
    stock_item_result = await AllocationService.confirm_allocation(payload, user, redis, db)
    
    # Verify DB Add was called with correct expiry
    added_items = [args[0] for args, _ in db.add.call_args_list]
    if added_items:
         item = added_items[0]
         print(f"StockItem Created: Product={item.product_id}, Expiry={item.expiry_date}")
         
         # Check expiry
         expected_expiry_min = datetime.now() + timedelta(days=29)
         expected_expiry_max = datetime.now() + timedelta(days=31)
         
         if expected_expiry_min <= item.expiry_date <= expected_expiry_max:
             print("✅ Expiry date is correct (within expected range)!")
         else:
             print(f"❌ Expiry date incorrect! Expected around {expected_expiry_min} - {expected_expiry_max}, got {item.expiry_date}")
             
         assert item.product_id == product.id
         print("✅ StockItem has correct product_id!")
         
    else:
        print("❌ db.add not called!")

    # Verify return type is Pydantic compatiable (implicit check via return type hint in actual code being verified by Pydantic if called via FastAPI, here we check attributes)
    # The return type of confirm_allocation is StockOut (Pydantic model) BUT implementation returns stock_item (ORM model).
    # FastAPI handles the conversion if response_model is set.
    # We should verify that stock_item has the attributes required by StockOut.
    
    print(f"Returned object: {stock_item_result}")
    
    # Check attributes requried by StockOut
    # id, product, rack_id, position_row, position_col, entry_date, expiry_date, received_by
    
    assert hasattr(stock_item_result, 'product')
    assert stock_item_result.product == product
    assert hasattr(stock_item_result, 'received_by')
    assert stock_item_result.received_by == user
    print("✅ Returned object has required attributes for StockOut schema!")

if __name__ == "__main__":
    asyncio.run(main())
