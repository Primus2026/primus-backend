from app.schemas.stock import StockOut
from app.schemas.stock import RackLocation
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database.models.product_definition import ProductDefinition, FrequencyClass
from app.database.models.rack import Rack
from app.database.models.stock_item import StockItem
from app.database.models.user import User
from app.schemas.allocation import AllocationResponse
from fastapi import HTTPException
from redis.asyncio import Redis
from app.core.config import settings
from app.schemas.user import UserReceiverOut
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger("ALLOCATION_SERVICE")

class AllocationService:

    @staticmethod
    async def allocate_item(
        db: AsyncSession, 
        barcode: str, 
        user: User, 
        redis_client: Redis
    ) -> AllocationResponse:
        
        # 1. Product Lookup
        stmt = select(ProductDefinition).where(ProductDefinition.barcode == barcode)
        result = await db.execute(stmt)
        product = result.scalars().first()
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Produkt o kodzie kreskowym {barcode} nie istnieje")

        # 2. Get all racks
        result = await db.execute(select(Rack))
        racks = result.scalars().all()
        
        if not racks:
            raise HTTPException(status_code=400, detail="W magazynie nie ma zdefiniowanych regałów")

        # 3. Filter Racks (Physical Requirements)
        pre_candidate_racks = []
        for rack in racks:
            SAFE_BUFFER = 2.0 

            overlap_min = max(rack.temp_min, product.req_temp_min)
            overlap_max = min(rack.temp_max, product.req_temp_max)

            if (overlap_max - overlap_min) < SAFE_BUFFER:
                continue
                
            if not (product.dims_x_mm <= rack.max_dims_x_mm and 
                    product.dims_y_mm <= rack.max_dims_y_mm and
                    product.dims_z_mm <= rack.max_dims_z_mm):
                continue
            
            if product.weight_kg > rack.max_weight_kg:
                continue

            pre_candidate_racks.append(rack)
            
        if not pre_candidate_racks:
            raise HTTPException(status_code=400, detail="Nie znaleziono regałów spełniających wymagań fizycznych")
            
        candidate_ids = [r.id for r in pre_candidate_racks]
        
        weight_stmt = (
            select(StockItem.rack_id, func.sum(ProductDefinition.weight_kg))
            .join(ProductDefinition, StockItem.product_id == ProductDefinition.id)
            .where(StockItem.rack_id.in_(candidate_ids))
            .group_by(StockItem.rack_id)
        )
        weight_result = await db.execute(weight_stmt)
        current_weights = {row[0]: row[1] or 0.0 for row in weight_result.all()}
        
        candidate_racks = []
        for rack in pre_candidate_racks:
            current_load = current_weights.get(rack.id, 0.0)
            if current_load + product.weight_kg <= rack.max_weight_kg:
                candidate_racks.append(rack)
                
        if not candidate_racks:
             raise HTTPException(status_code=400, detail="Limit wagowy regału osiągnięty")

        # 4. Znajdź wszystkie możliwe miejsca we wszystkich pasujących regałach
        possible_placements = []
        
        for rack in candidate_racks:
            stmt_occupied = select(StockItem.position_row, StockItem.position_col, StockItem.y_position, StockItem.product_id).where(StockItem.rack_id == rack.id)
            result_occupied = await db.execute(stmt_occupied)
            occupied = result_occupied.fetchall()
            
            grid_state = {}
            for occ_row, occ_col, occ_y, occ_prod_id in occupied:
                if (occ_row, occ_col) not in grid_state:
                    grid_state[(occ_row, occ_col)] = {'max_y': occ_y, 'product_id_at_0': None}
                else:
                    grid_state[(occ_row, occ_col)]['max_y'] = max(grid_state[(occ_row, occ_col)]['max_y'], occ_y)
                
                if occ_y == 0:
                    grid_state[(occ_row, occ_col)]['product_id_at_0'] = occ_prod_id
                    
            # Iterujemy po magazynie (wyłączamy rzad 1)
            for r in range(2, rack.rows_m + 1):
                for c in range(1, rack.cols_n + 1):
                    state = grid_state.get((r, c), {'max_y': -1, 'product_id_at_0': None})
                    dist = abs(r - 1) + abs(c - 2) # Dystans do "01" (row=1, col=2)
                    
                    if state['max_y'] == -1: # Puste pole
                        possible_placements.append({"rack": rack, "row": r, "col": c, "y_position": 0, "dist": dist, "is_stack": False})
                    elif state['max_y'] == 0 and state['product_id_at_0'] == product.id: # Miejsce z gotowym 1 el na spodzie = mozna stakowac
                        possible_placements.append({"rack": rack, "row": r, "col": c, "y_position": 1, "dist": dist, "is_stack": True})

        if not possible_placements:
            raise HTTPException(status_code=400, detail="Nie znaleziono wolnego miejsca w odpowiednich regałach")

        # 5. Strategia wg FrequencyClass
        if product.frequency_class == FrequencyClass.A:
            # stacking always first, then closest
            sort_key = lambda p: (not p['is_stack'], p['dist'])
        elif product.frequency_class == FrequencyClass.C:
            # stacking always first, then furthest
            sort_key = lambda p: (not p['is_stack'], -p['dist'])
        else: # B
            # stacking always first, then median approx 7
            sort_key = lambda p: (not p['is_stack'], abs(p['dist'] - 7))

        possible_placements.sort(key=sort_key)
        best_slot = possible_placements[0]

        return AllocationResponse(
            rack_id=best_slot['rack'].id,
            rack_designation=best_slot['rack'].designation,
            row=best_slot['row'],
            col=best_slot['col'],
            y_position=best_slot['y_position']
        )
        
