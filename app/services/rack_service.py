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
        # Check if rack with same designation already exists
        result = await db.execute(select(Rack).where(Rack.designation == rack.designation))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Półka o tym oznaczeniu już istnieje")

        new_rack = Rack(**rack.dict())
        db.add(new_rack)
        await db.commit()
        await db.refresh(new_rack)
        return new_rack

    @staticmethod
    async def update_rack(db: AsyncSession, rack_id: int, rack: RackUpdate) -> Rack:      
        updatedRack = await db.get(Rack, rack_id)
        if not updatedRack:
            raise HTTPException(status_code=404, detail="Regał nie został znaleziony")

        # Check for duplicate designation ONLY if designation is being updated
        if rack.designation and rack.designation != updatedRack.designation:
            result = await db.execute(select(Rack).where(Rack.designation == rack.designation))
            same_designation = result.scalar_one_or_none()

            if same_designation:
                raise HTTPException(status_code=400, detail="Półka o tym oznaczeniu już istnieje")
        
        update_data = rack.model_dump(exclude_unset=True)
        # Remove id from update data to avoid overwriting it (though usually it's excluded or safe)
        if 'id' in update_data:
            del update_data['id']

        # --- VALIDATION AGAINST EXISTING ITEMS ---
        # Fetch aggregated stats of items currently on this rack
        stats_query = select(
            func.sum(ProductDefinition.weight_kg),
            func.max(ProductDefinition.dims_x_mm),
            func.max(ProductDefinition.dims_y_mm),
            func.max(ProductDefinition.dims_z_mm),
            func.max(ProductDefinition.req_temp_min),
            func.min(ProductDefinition.req_temp_max)
        ).join(StockItem, StockItem.product_id == ProductDefinition.id)\
         .where(StockItem.rack_id == rack_id)
        
        stats_result = await db.execute(stats_query)
        curr_stats = stats_result.one()
        curr_weight_sum, curr_max_x, curr_max_y, curr_max_z, max_req_min, min_req_max = curr_stats

        # Determine new values (merging update with existing)
        new_max_weight = update_data.get('max_weight_kg', updatedRack.max_weight_kg)
        new_max_x = update_data.get('max_dims_x_mm', updatedRack.max_dims_x_mm)
        new_max_y = update_data.get('max_dims_y_mm', updatedRack.max_dims_y_mm)
        new_max_z = update_data.get('max_dims_z_mm', updatedRack.max_dims_z_mm)
        new_temp_min = update_data.get('temp_min', updatedRack.temp_min)
        new_temp_max = update_data.get('temp_max', updatedRack.temp_max)

        validation_errors = []

        if curr_weight_sum is not None:
            if new_max_weight < curr_weight_sum:
                validation_errors.append(f"Maksymalna waga ({new_max_weight}kg) jest mniejsza niż aktualne obciążenie ({curr_weight_sum}kg)")
            
            if new_max_x < curr_max_x:
                validation_errors.append(f"Nowa szerokość ({new_max_x}mm) jest mniejsza niż najszerszego produktu ({curr_max_x}mm)")
            
            if new_max_y < curr_max_y:
                validation_errors.append(f"Nowa wysokość ({new_max_y}mm) jest mniejsza niż najwyższego produktu ({curr_max_y}mm)")
            
            if new_max_z < curr_max_z:
                validation_errors.append(f"Nowa głębokość ({new_max_z}mm) jest mniejsza niż najgłębszego produktu ({curr_max_z}mm)")

            # Temp Check Logic:
            # Rack must guarantee a temp range that is SAFE for the item.
            # Item needs [Tmin_req, Tmax_req]. Rack provides [Tmin_rack, Tmax_rack].
            # Safe means Rack's whole range must be within Item's supported range? 
            # OR likely: The Rack *maintainable* range must satisfy the Item.
            # Usually: 
            #  - The rack's MIN temp must be >= Item's MIN required (it shouldn't get colder than item allows)
            #  - The rack's MAX temp must be <= Item's MAX required (it shouldn't get hotter than item allows)
            
            if max_req_min is not None:
                # If rack's min temp is LOWER than the highest required min temp, some item might freeze/be too cold?
                # Actually earlier logic: Rack.temp_min >= max_req_min
                if new_temp_min < max_req_min:
                    validation_errors.append(f"Minimalna temperatura ({new_temp_min}) jest niższa niż wymagana minimalna ({max_req_min})")

            if min_req_max is not None:
                # If rack's max temp is HIGHER than the lowest required max temp, some item might overheat
                if new_temp_max > min_req_max:
                     validation_errors.append(f"Maksymalna temperatura ({new_temp_max}) jest wyższa niż wymagana maksymalna ({min_req_max})")

        if validation_errors:
            raise HTTPException(status_code=400, detail="Te wartości są nieprawidłowe dla produktów na tym regale")

        for key, value in update_data.items():
            setattr(updatedRack, key, value)

        # Validate business rules
        if updatedRack.temp_min is not None and updatedRack.temp_max is not None:
            if updatedRack.temp_min > updatedRack.temp_max:
                raise HTTPException(status_code=400, detail="Minimalna temperatura nie może być wyższa niż maksymalna temperatura")

        await db.commit()
        await db.refresh(updatedRack)
        return updatedRack

    @staticmethod
    async def delete_rack(db: AsyncSession, rack_id: int) -> Rack:
        rack = await db.get(Rack, rack_id)
        if not rack:
            raise HTTPException(status_code=404, detail="Regał nie został znaleziony")
        
        # Check if rack has items
        result = await db.execute(select(StockItem).where(StockItem.rack_id == rack_id).limit(1))
        if result.scalar_one_or_none():
             raise HTTPException(status_code=400, detail="Regał ma produkty, musi być pusty")
        
        await db.delete(rack)
        await db.commit()
        return rack

    @staticmethod
    async def get_rack(db: AsyncSession, rack_id: int) -> Rack:
        rack = await db.get(Rack, rack_id)
        if not rack:
            raise HTTPException(status_code=404, detail="Regał nie został znaleziony")
        return rack

    @staticmethod
    async def process_csv_import(file_content: bytes, db: AsyncSession):
        from app.schemas.rack import RackCSVRow, RackImportSummary, RackImportResult
        import csv
        import io
        from sqlalchemy.orm import selectinload

        # Decode content
        try:
            content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Invalid file encoding, must be UTF-8")

        # Parse CSV
        rows = []
        try:
            processed_lines = []
            header_found = False
            
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                
                # Jeśli linia to nagłówek (zawiera nasze kluczowe słowa), 
                # usuwamy '#' i traktujemy jako normalną linię
                if "Oznaczenie;M;N;" in stripped:
                    processed_lines.append(stripped.lstrip("#"))
                    header_found = True
                # Jeśli to zwykły komentarz, pomijamy
                elif stripped.startswith("#"):
                    continue
                else:
                    processed_lines.append(stripped)

            if not header_found:
                raise ValueError("Nie znaleziono linii nagłówkowej w pliku CSV.")

            reader = csv.DictReader(processed_lines, delimiter=";")
            for row_dict in reader:
                # Filtracja pustych kluczy
                clean_row = {k: v.strip() if v else v for k, v in row_dict.items() if k}
                if not clean_row.get("Oznaczenie"): # Pomijaj puste linie
                    continue
                rows.append(RackCSVRow.model_validate(clean_row))
        except Exception as e:

            raise ValueError(f"CSV Parsing Error: {str(e)}")

        if not rows:
             raise ValueError("CSV is empty or contains no valid data")

        summary = RackImportSummary()
        valid_updates = []
        new_racks = []
        
        # Fetch all racks to memory to separate NEW vs EXISTING (assuming reasonable count < 1000s)
        
        existing_result = await db.execute(select(Rack))
        existing_racks = {r.designation: r for r in existing_result.scalars().all()}
        
        # Identify New vs Updates and Collect IDs for Bulk Stats
        total_updates_attempted = 0
        conflicts_count = 0
        
        # Collect IDs of racks being updated to fetch their stats in bulk
        update_rack_ids = [existing_racks[r.designation].id for r in rows if r.designation in existing_racks]
        
        # Bulk Fetch Stats
        rack_stats_map = {}
        
        if update_rack_ids:
            stats_query = select(
                StockItem.rack_id,
                func.sum(ProductDefinition.weight_kg),
                func.max(ProductDefinition.dims_x_mm),
                func.max(ProductDefinition.dims_y_mm),
                func.max(ProductDefinition.dims_z_mm),
                func.max(ProductDefinition.req_temp_min),
                func.min(ProductDefinition.req_temp_max)  
            ).join(StockItem, StockItem.product_id == ProductDefinition.id)\
             .where(StockItem.rack_id.in_(update_rack_ids))\
             .group_by(StockItem.rack_id)
             
            stats_result = await db.execute(stats_query)
            for s_row in stats_result.all():
                # s_row = (rack_id, weight, x, y, z, min_t, max_t)
                rack_stats_map[s_row[0]] = s_row[1:]

        for row in rows:
            if row.designation in existing_racks:
                rack = existing_racks[row.designation]
                total_updates_attempted += 1
                
                # Check collisions using Bulk Map
                stats = rack_stats_map.get(rack.id)
                
                # If there are items (stats found)
                if stats:
                    curr_weight, curr_max_x, curr_max_y, curr_max_z, min_temp, max_temp = stats
                    
                    if curr_weight is not None:
                        conflict_reasons = []
                        
                        # Weight Check
                        if row.max_weight < curr_weight:
                            conflict_reasons.append(f"New max weight {row.max_weight}kg < current load {curr_weight}kg")
                        
                        # Dimensions Check
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
             raise ValueError(f"Too many conflicts ({conflicts_count}/{len(rows)}). Aborting import.")

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
        
        return RackImportResult(message="Import completed successfully", summary=summary)

    @staticmethod 
    async def get_all_racks(db: AsyncSession) -> list[Rack]:
        result = await db.execute(select(Rack))
        return result.scalars().all()

    @staticmethod
    async def get_racks_with_inventory(db: AsyncSession):
        from app.schemas.rack import RackWithInventory, RackSlotWeight
        
        # Fetch all racks
        racks_result = await db.execute(select(Rack))
        racks = racks_result.scalars().all()
        
        # Fetch all active stock items joined with ProductDefinition to get weight
        stmt = select(
            StockItem.rack_id,
            StockItem.position_row,
            StockItem.position_col,
            ProductDefinition.weight_kg
        ).join(ProductDefinition, StockItem.product_id == ProductDefinition.id)
        
        items_result = await db.execute(stmt)
        items = items_result.all()
        
        # Map items to rack_id
        items_by_rack = {}
        for rack_id, row, col, weight in items:
            if rack_id not in items_by_rack:
                items_by_rack[rack_id] = []
            items_by_rack[rack_id].append(RackSlotWeight(row=row, col=col, current_weight=weight))
            
        # Construct result
        results = []
        for rack in racks:
            # We explicitly map fields to ensure RackWithInventory is correctly populated
            # since the source 'rack' is a SQLAlchemy model and target has extra field 'active_slots'
            rack_data = RackWithInventory(
                id=rack.id,
                designation=rack.designation,
                rows_m=rack.rows_m,
                cols_n=rack.cols_n,
                temp_min=rack.temp_min,
                temp_max=rack.temp_max,
                max_weight_kg=rack.max_weight_kg,
                max_dims_x_mm=rack.max_dims_x_mm,
                max_dims_y_mm=rack.max_dims_y_mm,
                max_dims_z_mm=rack.max_dims_z_mm,
                comment=rack.comment,
                distance_from_exit_m=rack.distance_from_exit_m,
                active_slots=items_by_rack.get(rack.id, [])
            )
            results.append(rack_data)
            
        return results

    @staticmethod
    async def get_rack_stock_items(db: AsyncSession, rack_id: int):
        from app.database.models.stock_item import StockItem
        from sqlalchemy.orm import selectinload

        # Check if rack exists
        await RackService.get_rack(db, rack_id)

        stmt = (
            select(StockItem)
            .where(StockItem.rack_id == rack_id)
            .options(
                selectinload(StockItem.product),
                selectinload(StockItem.receiver)
            )
        )
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        results = []
        for item in items:
            # Manually map the relationship to the schema field name
            # StockOut expects "received_by"
            item_data = {
                "id": item.id,
                "product": item.product,
                "rack_id": item.rack_id,
                "position_row": item.position_row,
                "position_col": item.position_col,
                "entry_date": item.entry_date,
                "expiry_date": item.expiry_date.date() if hasattr(item.expiry_date, 'date') else item.expiry_date,
                "received_by": item.receiver,
                "y_position": item.y_position
            }
            results.append(item_data)
            
        return results