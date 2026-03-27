import logging
import asyncio
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload 
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.stock_item import StockItem
from app.database.models.rack import Rack
from app.database.models.product_definition import ProductDefinition
from app.services.camera_service import camera
from app.services.gcode_service import gcode
from app.services.product_stats_service import ProductStatsService

logger = logging.getLogger("InventoryService")

class InventoryService:
    @staticmethod
    async def audit_inventory(db: AsyncSession):
        result = await db.execute(select(Rack).where(Rack.designation == "PRINTER_3D"))
        rack = result.scalars().first()
        if not rack:
            return {"status": "error", "message": "Rack PRINTER_3D not found"}

        # Pobieramy wszystko z bazy
        stmt = select(StockItem).where(StockItem.rack_id == rack.id).options(selectinload(StockItem.product))
        db_items_result = await db.execute(stmt)
        db_items = db_items_result.scalars().all()
        
        # Mapa: (db_row, col) -> StockItem
        db_map = {(item.position_row, item.position_col): item for item in db_items}

        report = []
        gcode.home()

        for row in range(2, 9):
            columns = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            for col in columns:
                gcode.move_camera_to_grid(col=col, row=row)
                await asyncio.sleep(0.6)

                detected_barcode = camera.decode_qr() or camera.recognize_pictogram()
                
                # POPRAWIONE: Dopasowanie fizycznego skanu (2-8) do rekordu w bazie (1-7)
                db_item = db_map.get((row - 1, col))
                db_barcode = db_item.product.barcode if db_item else None

                slot_status = {
                    "row": row, # Fizyczny rząd dla frontendu
                    "col": col,
                    "db_barcode": db_barcode,
                    "physical_barcode": detected_barcode,
                    "is_correct": True,
                    "error_message": None
                }

                if not detected_barcode and not db_barcode:
                    slot_status["error_message"] = "Puste"
                elif detected_barcode and not db_barcode:
                    slot_status["is_correct"] = False
                    slot_status["error_message"] = f"Nadmiar: Wykryto {detected_barcode}, brak w systemie"
                elif not detected_barcode and db_barcode:
                    slot_status["is_correct"] = False
                    slot_status["error_message"] = f"Brak: System widzi {db_barcode}, pole jest puste"
                elif detected_barcode != db_barcode:
                    slot_status["is_correct"] = False
                    slot_status["error_message"] = f"Mismatch: System: {db_barcode}, Fizycznie: {detected_barcode}"
                else:
                    slot_status["error_message"] = "Zgodne"

                report.append(slot_status)

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_slots": len(report),
                "errors_found": len([s for s in report if not s["is_correct"]])
            },
            "details": report
        }
    @staticmethod
    async def run_full_inventory(db: AsyncSession, user_id: int):
        """
        Przeprowadza pełną inwentaryzację rzędów magazynowych 2-8 na drukarce PRINTER_3D.
        Rząd 1 jest zarezerwowany na INBOUND/OUTBOUND.
        """
        # 1. Pobierz lub sprawdź regał PRINTER_3D
        result = await db.execute(select(Rack).where(Rack.designation == "PRINTER_3D"))
        rack = result.scalars().first()
        if not rack:
            logger.error("Regał PRINTER_3D nie istnieje w bazie!")
            return {"status": "error", "message": "Rack PRINTER_3D not found"}

        # Home drukarki przed startem
        gcode.home()

        # 2. Pętla inwentaryzacji (Wiersze fizyczne 2-8)
        for row in range(2, 9):
            # Optymalizacja trasy (snake pattern)
            columns = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            
            for col in columns:
                logger.info(f"Skanowanie pola: R{row} C{col}")
                
                # Ruch kamerą nad pole
                gcode.move_camera_to_grid(col=col, row=row)
                await asyncio.sleep(0.5) # Krótka pauza na stabilizację kamery

                # Próba detekcji: QR -> Figura
                detected_barcode = camera.decode_qr()
                if not detected_barcode:
                    detected_barcode = camera.recognize_pictogram()

                if detected_barcode:
                    # ZNALEZIONO PRODUKT
                    await InventoryService._handle_found_item(
                        db, rack.id, row, col, detected_barcode, user_id
                    )
                
                # WYMUSZENIE SYNCHRONIZACJI Z BAZĄ
                await db.flush()

        await db.commit()
        return {"status": "success", "message": "Inwentaryzacja rzędów 2-8 zakończona"}

    @staticmethod
    async def _handle_found_item(db: AsyncSession, rack_id: int, row: int, col: int, barcode: str, user_id: int):
        """Aktualizuje bazę. Przyjmuje row(2-8), col(1-8). Zapisuje DB_row(1-7), DB_col(1-8)."""
        prod_result = await db.execute(
            select(ProductDefinition).where(ProductDefinition.barcode == barcode)
        )
        product = prod_result.scalars().first()
        
        if not product:
            logger.warning(f"Wykryto kod {barcode}, ale nie ma takiej definicji w bazie.")
            return

        # KONWENCJA: DB Row = Physical Row - 1 | DB Col = Physical Col
        db_row, db_col = row - 1, col
        existing_stmt = select(StockItem).where(
            StockItem.rack_id == rack_id,
            StockItem.position_row == db_row,
            StockItem.position_col == db_col,
            StockItem.y_position == 0
        )
        existing_item = (await db.execute(existing_stmt)).scalars().first()

        if existing_item:
            if existing_item.product_id == product.id:
                return
            else:
                await db.delete(existing_item)

        new_item = StockItem(
            product_id=product.id,
            rack_id=rack_id,
            position_row=db_row,
            position_col=db_col,
            y_position=0,
            received_by_id=user_id,
            expiry_date=datetime.now()
        )
        db.add(new_item)
        logger.info(f"Zaktualizowano: {barcode} na R{row} C{col} (DB: row={db_row}, col={db_col})")