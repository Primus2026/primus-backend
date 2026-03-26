from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
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
from datetime import datetime, timedelta
from app.services.camera_service import camera
from app.services.gcode_service import gcode
from app.services.allocation_service import AllocationService


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
    async def direct_remove(barcode: str, user: User, redis_client: Redis, db: AsyncSession):
        from app.services.gcode_service import gcode
        
        # 1. Znalezienie fizycznie najstarszego (FIFO) przedmiotu tego kodu
        stmt = (
            select(StockItem)
            .options(selectinload(StockItem.rack))
            .join(ProductDefinition)
            .where(ProductDefinition.barcode == barcode)
            .order_by(StockItem.entry_date.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        item_to_remove = result.scalars().first()
        
        if not item_to_remove:
            raise HTTPException(status_code=404, detail="Produkt nie został znaleziony")
            
        product_id = item_to_remove.product_id
        rack = item_to_remove.rack
        R = item_to_remove.position_row
        C = item_to_remove.position_col
        
        # 2. Sprawdzenie, czy ten konkretny przedmiot ma coś na sobie (y_position == 1 na tej samej kratce)
        # UWAGA: Szukamy tylko na tym samym regale i w tej samej kolumnie/wierszu, ale poziom wyżej
        stmt_top = (
            select(StockItem)
            .where(
                StockItem.rack_id == rack.id,
                StockItem.position_row == R,
                StockItem.position_col == C,
                StockItem.y_position == 1
            )
        )
        result_top = await db.execute(stmt_top)
        top_item = result_top.scalars().first()
            
        try:
            if top_item:
                # SCENARIUSZ A: Podwójne składowanie (zdejmujemy dół, góra zostaje)
                logger.info(f"Odkrywamy dół: [{R}, {C}, y=0] wyjeżdża, [{R}, {C}, y=1] spada na y=0.")

                # --- ROBOTYKA (G-Code) ---
                # 1. Weź górny element i odstaw go tymczasowo (lub trzymaj w chwytaku)
                # Tu używamy Twojej logiki temp_R/temp_C jeśli chcesz go fizycznie odstawić
                # Albo po prostu symulujemy procedurę:
                gcode.pick_from_grid(col=C, row=R, level=1)
                gcode.place_on_grid(col=2, row=2, level=0) # Miejsce techniczne
                
                # 2. Wyciągnij dolny (docelowy) i daj na wyjście
                gcode.pick_from_grid(col=C, row=R, level=0)
                gcode.place_on_grid(col=2, row=1, level=0) # Wyjście
                
                # 3. Odstaw górny z powrotem na to samo miejsce, ale teraz na poziom 0
                gcode.pick_from_grid(col=2, row=2, level=0)
                gcode.place_on_grid(col=C, row=R, level=0)

                # --- BAZA DANYCH ---
                # KLUCZ: Najpierw usuwamy dolny, żeby zwolnić constraint y=0
                await db.delete(item_to_remove)
                await db.flush() # Wysyła DELETE do bazy, ale nie kończy transakcji

                # Teraz możemy bezpiecznie zmienić y_position górnego na 0
                top_item.y_position = 0
                
            else:
                # SCENARIUSZ B: Pojedynczy przedmiot (lub przedmiot był na y=1)
                logger.info(f"Pojedyncze wydanie: [{R}, {C}, y={item_to_remove.y_position}]")
                
                gcode.pick_from_grid(col=C, row=R, level=item_to_remove.y_position)
                gcode.place_on_grid(col=2, row=1, level=0)
                
                await db.delete(item_to_remove)

        except Exception as e:
            await db.rollback()
            logger.error(f"G-Code Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Błąd operacji: {str(e)}")
            
        # 5. Finalizacja
        await db.commit()
        
        # Statystyki i Redis
        await ProductStatsService.update_product_stats(db, product_id, 1, redis_client)
        
        # Pobranie wagi do aktualizacji Redisa
        stmt_prod = select(ProductDefinition.weight_kg).where(ProductDefinition.id == product_id)
        prod_weight = (await db.execute(stmt_prod)).scalar_one()
        
        await redis_client.hincrby(f"Rack:{rack.designation}", "weight_kg", int(-prod_weight))
        await redis_client.delete(f"Weight:{rack.designation}:{R}:{C}")
        
        return Msg(message="Produkt wydany. Element nadrzędny został przesunięty na poziom 0.")
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

        return Msg(message="Produkt został usunięty pomyślnie")

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

        return Msg(message="Proces wydawania asortymentu został anulowany pomyślnie")

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

    @staticmethod
    async def auto_inbound_process(db: AsyncSession, user: User, redis_client: Redis):
        """
        Automatyczne przyjęcie: 
        1. Podjazd nad pole Inbound (1,1).
        2. Rozpoznanie QR/Piktogramu.
        3. Alokacja i fizyczne odłożenie.
        """
        # 1. Ruch kamery nad pole Inbound (Slot 1,1)
        # Zakładamy, że produkt leży fizycznie na polu 1,1 (współrzędne 0,0 w systemie 0-7)
        gcode.move_camera_to_grid(col=1, row=1)
        await asyncio.sleep(0.8) # Czas na focus kamery

        # 2. Próba rozpoznania produktu
        barcode = camera.decode_qr()
        if not barcode:
            barcode = camera.recognize_pictogram()
            
        if not barcode:
            raise HTTPException(
                status_code=404, 
                detail="Nie wykryto żadnego produktu (QR ani piktogramu) na polu Inbound."
            )

        logger.info(f"Auto-Inbound wykrył produkt: {barcode}")

        # 3. Wykorzystanie logiki Alokacji (znalezienie miejsca)
        allocation = await AllocationService.allocate_item(
            db=db,
            barcode=barcode,
            user=user,
            redis_client=redis_client
        )

        # 4. Pobranie definicji produktu
        stmt = select(ProductDefinition).where(ProductDefinition.barcode == barcode)
        result = await db.execute(stmt)
        product = result.scalars().first()
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Wykryto {barcode}, ale brak definicji w bazie.")

        # 5. Fizyczny ruch (Pick & Place)
        try:
            pass
            # Pobranie ze slotu 1,1 (Inbound)
            # gcode.pick_from_grid(col=1, row=1, level=0)
            # # Odłożenie na miejsce docelowe
            # gcode.place_on_grid(col=allocation.col, row=allocation.row, level=allocation.y_position)
        except Exception as e:
            logger.error(f"G-Code Error: {e}")
            raise HTTPException(status_code=500, detail=f"Błąd mechaniczny drukarki: {str(e)}")

        # 6. Zapis do bazy danych
        stock_item = StockItem(
            rack_id=allocation.rack_id,
            position_row=allocation.row,
            position_col=allocation.col,
            y_position=allocation.y_position,
            product_id=product.id,
            entry_date=datetime.now(),
            expiry_date=(datetime.now() + timedelta(days=product.expiry_days)).date(),
            received_by_id=user.id
        )
        
        db.add(stock_item)
        await db.commit()
        await db.refresh(stock_item, ["product", "receiver"])
        
        # AKTUALIZACJA REDIS (zostaje bez zmian)
        await redis_client.hincrby(f"Rack:{allocation.rack_designation}", "weight_kg", int(product.weight_kg))
        await redis_client.set(f"Weight:{allocation.rack_designation}:{allocation.row}:{allocation.col}", product.weight_kg)
        
        # POPRAWKA TUTAJ: Mapujemy 'receiver' na 'received_by'
        return {
            "id": stock_item.id,
            "product": stock_item.product,
            "rack_id": stock_item.rack_id,
            "position_row": stock_item.position_row,
            "position_col": stock_item.position_col,
            "y_position": stock_item.y_position,
            "entry_date": stock_item.entry_date,
            "expiry_date": stock_item.expiry_date,
            "received_by": stock_item.receiver  # Mapujemy relację na pole oczekiwane przez schemat
        } 