from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.database.models.rack import Rack
from app.schemas.rack import RackCreate, RackUpdate

from app.database.models.stock_item import StockItem
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import func

class RackService:
    @staticmethod
    async def create_rack(db: AsyncSession, rack: RackCreate) -> Rack:
        new_rack = Rack(**rack.dict())
        db.add(new_rack)
        await db.commit()
        await db.refresh(new_rack)
        return new_rack

    @staticmethod
    async def update_rack(db: AsyncSession, rack: RackUpdate) -> Rack:      
        updatedRack = await db.get(Rack, rack.id)
        if not updatedRack:
            raise HTTPException(status_code=404, detail="Rack not found")

        # Check for duplicate designation ONLY if designation is being updated
        if rack.designation and rack.designation != updatedRack.designation:
            result = await db.execute(select(Rack).where(Rack.designation == rack.designation))
            same_designation = result.scalar_one_or_none()

            if same_designation:
                raise HTTPException(status_code=400, detail="Rack with this designation already exists")
        
        update_data = rack.dict(exclude_unset=True)
        # Remove id from update data to avoid overwriting it (though usually it's excluded or safe)
        if 'id' in update_data:
            del update_data['id']

        for key, value in update_data.items():
            setattr(updatedRack, key, value)

        await db.commit()
        await db.refresh(updatedRack)
        return updatedRack

    @staticmethod
    async def delete_rack(db: AsyncSession, rack_id: int) -> Rack:
        rack = await db.get(Rack, rack_id)
        if not rack:
            raise HTTPException(status_code=404, detail="Rack not found")
        
        # Check if rack has items
        result = await db.execute(select(StockItem).where(StockItem.rack_id == rack_id).limit(1))
        if result.scalar_one_or_none():
             raise HTTPException(status_code=400, detail="Rack has items, has to be empty")
        
        await db.delete(rack)
        await db.commit()
        return rack

    @staticmethod
    async def get_rack(db: AsyncSession, rack_id: int) -> Rack:
        rack = await db.get(Rack, rack_id)
        if not rack:
            raise HTTPException(status_code=404, detail="Rack not found")
        return rack

    @staticmethod
    async def process_csv_import(file_content: bytes, db: AsyncSession):
        from app.schemas.csv_import import RackCSVRow, ImportSummary, ImportResult
        import csv
        import io
        from sqlalchemy.orm import selectinload

        # Decode content
        try:
            content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid file encoding, must be UTF-8")

        # Parse CSV
        rows = []
        try:
            # Skip lines starting with # before parsing
            lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
            reader = csv.DictReader(lines, delimiter=";")
            for row_dict in reader:
                # Filter out None/empty keys if any
                clean_row = {k: v for k, v in row_dict.items() if k}
                rows.append(RackCSVRow.model_validate(clean_row))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV Parsing Error: {str(e)}")

        if not rows:
             raise HTTPException(status_code=400, detail="CSV is empty or contains no valid data")

        summary = ImportSummary()
        valid_updates = []
        new_racks = []
        
        # Fetch all racks to memory to separate NEW vs EXISTING (assuming reasonable count < 1000s)
        
        existing_result = await db.execute(select(Rack))
        existing_racks = {r.designation: r for r in existing_result.scalars().all()}
        
        # Identify New vs Updates
        total_updates_attempted = 0
        conflicts_count = 0
        
        for row in rows:
            if row.designation in existing_racks:
                rack = existing_racks[row.designation]
                total_updates_attempted += 1
                
                # Check collisions with Aggregate Query (Optimization)
                # We fetch the stats of current items in one go:
                # - Total Weight
                # - Max Dimensions (x, y, z)
                # - Temp Constraints (Highest Min, Lowest Max)
                
                stats_query = select(
                    func.sum(ProductDefinition.weight_kg),
                    func.max(ProductDefinition.dims_x_mm),
                    func.max(ProductDefinition.dims_y_mm),
                    func.max(ProductDefinition.dims_z_mm),
                    func.max(ProductDefinition.req_temp_min),
                    func.min(ProductDefinition.req_temp_max)  
                ).join(StockItem, StockItem.product_id == ProductDefinition.id).where(StockItem.rack_id == rack.id)

                stats_result = await db.execute(stats_query)
                curr_weight, curr_max_x, curr_max_y, curr_max_z, min_temp, max_temp = stats_result.one()

                # If there are items (curr_weight will be not None)
                if curr_weight is not None:
                    conflict_reasons = []
                    
                    # Weight Check
                    if row.max_weight < curr_weight:
                        conflict_reasons.append(f"New max weight {row.max_weight}kg < current load {curr_weight}kg")
                    
                    # Dimensions Check (The rack must fit the largest item)
                    # Note: We compare max item dimension to max rack dimension on same axis. 
                    if row.max_width < curr_max_x:
                        conflict_reasons.append(f"New width {row.max_width}mm < item width {curr_max_x}mm")
                    if row.max_height < curr_max_y:
                        conflict_reasons.append(f"New height {row.max_height}mm < item height {curr_max_y}mm")
                    if row.max_depth < curr_max_z:
                         conflict_reasons.append(f"New depth {row.max_depth}mm < item depth {curr_max_z}mm")

                    # Temp Check
                    if min_temp is not None:
                        if row.temp_min < min_temp: 
                             conflict_reasons.append(f"New temp min {row.temp_min} < item min req {min_temp}")
                        
                        if row.temp_max > max_temp:
                             conflict_reasons.append(f"New temp max {row.temp_max} > item max req {max_temp}")

                    if conflict_reasons:
                        conflicts_count += 1
                        summary.skipped_count += 1
                        summary.skipped_details.append(f"Rack {row.designation}: {'; '.join(conflict_reasons)}")
                        continue # Skip this update
                
                valid_updates.append((rack, row))
            else:
                new_racks.append(row)

        # Threshold Check
        if len(rows) > 0 and (conflicts_count / len(rows)) > 0.30:
             raise HTTPException(status_code=400, detail=f"Too many conflicts ({conflicts_count}/{len(rows)}). Aborting import.")

        # Apply Changes
        for rack, row in valid_updates:
            rack.rows_m = row.rows
            rack.cols_n = row.cols
            rack.temp_min = row.temp_min
            rack.temp_max = row.temp_max
            rack.max_weight_kg = row.max_weight
            rack.max_dims_x_mm = row.max_width
            rack.max_dims_y_mm = row.max_height
            rack.max_dims_z_mm = row.max_depth
            rack.comment = row.comment
            summary.updated_count += 1

        for row in new_racks:
            new_rack = Rack(
                designation=row.designation,
                rows_m=row.rows,
                cols_n=row.cols,
                temp_min=row.temp_min,
                temp_max=row.temp_max,
                max_weight_kg=row.max_weight,
                max_dims_x_mm=row.max_width,
                max_dims_y_mm=row.max_height,
                max_dims_z_mm=row.max_depth,
                comment=row.comment
            )
            db.add(new_rack)
            summary.created_count += 1

        await db.commit()
        
        return ImportResult(message="Import completed successfully", summary=summary)