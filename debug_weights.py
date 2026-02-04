
import asyncio
from app.database.session import SessionLocal
from sqlalchemy import select, func
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition

async def check_weights():
    async with SessionLocal() as db:
        print("--- Checking Racks and Weights ---")
        stmt = select(Rack)
        racks = (await db.execute(stmt)).scalars().all()
        
        for rack in racks:
            # Calculate weight
            weight_stmt = (
                select(func.sum(ProductDefinition.weight_kg))
                .select_from(StockItem)
                .join(ProductDefinition, StockItem.product_id == ProductDefinition.id)
                .where(StockItem.rack_id == rack.id)
            )
            weight = (await db.execute(weight_stmt)).scalar() or 0.0
            
            # Count items
            count_stmt = select(func.count(StockItem.id)).where(StockItem.rack_id == rack.id)
            count = (await db.execute(count_stmt)).scalar() or 0
            
            print(f"Rack {rack.designation} (ID: {rack.id}):")
            print(f"  Max Weight: {rack.max_weight_kg} kg")
            print(f"  Current Weight (DB): {weight} kg")
            print(f"  Items Count: {count}")
            print(f"  Remaining: {rack.max_weight_kg - weight} kg")
            
            if count > 0:
                print("  Items:")
                items_stmt = select(StockItem, ProductDefinition).join(ProductDefinition).where(StockItem.rack_id == rack.id)
                items = (await db.execute(items_stmt)).all()
                for item, prodef in items:
                    print(f"    - ID: {item.id}, Product: {prodef.name}, Weight: {prodef.weight_kg} kg")

        print("\n--- Simulating Allocation for Sos śmietanowy ---")
        # Sos śmietanowy barcode 564823902
        prod_stmt = select(ProductDefinition).where(ProductDefinition.barcode == "564823902")
        product = (await db.execute(prod_stmt)).scalar_one_or_none()
        if product:
            print(f"Product: {product.name} ({product.weight_kg}kg, {product.req_temp_min}-{product.req_temp_max}C)")
            pre_candidates = []
            for rack in racks:
                print(f"Checking Rack {rack.designation}:")
                
                # Temp Check
                temp_ok = (rack.temp_min >= product.req_temp_min and rack.temp_max <= product.req_temp_max)
                print(f"  Temp ({rack.temp_min}-{rack.temp_max} vs {product.req_temp_min}-{product.req_temp_max}): {temp_ok}")
                
                # Dims Check
                dims_ok = (product.dims_x_mm <= rack.max_dims_x_mm and 
                           product.dims_y_mm <= rack.max_dims_y_mm and
                           product.dims_z_mm <= rack.max_dims_z_mm)
                print(f"  Dims: {dims_ok}")
                
                # Weight Check
                weight_ok = (product.weight_kg <= rack.max_weight_kg)
                print(f"  Single Weight: {weight_ok}")
                
                if temp_ok and dims_ok and weight_ok:
                    print("  -> Passed Pre-Candidate")
                    pre_candidates.append(rack)
                else:
                    print("  -> REJECTED")

            print(f"\nPre-Candidates count: {len(pre_candidates)}")
            
            # Check Capacity
            candidates = []
            for rack in pre_candidates:
                weight_stmt = (
                    select(func.sum(ProductDefinition.weight_kg))
                    .select_from(StockItem)
                    .join(ProductDefinition, StockItem.product_id == ProductDefinition.id)
                    .where(StockItem.rack_id == rack.id)
                )
                current_weight = (await db.execute(weight_stmt)).scalar() or 0.0
                
                fits = (current_weight + product.weight_kg <= rack.max_weight_kg)
                print(f"Rack {rack.designation}: Current {current_weight} + New {product.weight_kg} <= Max {rack.max_weight_kg}? {fits}")
                if fits:
                    candidates.append(rack)
            
            print(f"Final Candidates count: {len(candidates)}")
        else:
            print("Product Sos śmietanowy not found")

if __name__ == "__main__":
    asyncio.run(check_weights())
