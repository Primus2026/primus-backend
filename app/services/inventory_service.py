import logging
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.stock_item import StockItem
from app.database.models.rack import Rack
from app.database.models.product_definition import ProductDefinition
from app.services.camera_service import camera
from app.services.gcode_service import gcode
from app.services.product_stats_service import ProductStatsService
from datetime import datetime

logger = logging.getLogger("InventoryService")

class InventoryService:
    @staticmethod
    async def audit_inventory(db: AsyncSession):
        """
        Etap 2: Porównanie stanu faktycznego z bazą danych bez wprowadzania zmian.
        Zwraca szczegółowy raport rozbieżności dla każdego pola.
        """
        # 1. Pobierz regał PRINTER_3D
        result = await db.execute(select(Rack).where(Rack.designation == "PRINTER_3D"))
        rack = result.scalars().first()
        if not rack:
            return {"status": "error", "message": "Rack PRINTER_3D not found"}

        # 2. Pobierz aktualny stan bazy dla tego regału
        stmt = select(StockItem).where(StockItem.rack_id == rack.id).options(selectinload(StockItem.product))
        db_items_result = await db.execute(stmt)
        db_items = db_items_result.scalars().all()
        
        # Mapa bazy danych dla szybkiego dostępu: (row, col) -> StockItem
        db_map = {(item.position_row, item.position_col): item for item in db_items}

        report = []
        gcode.home()

        # 3. Pętla skanowania (Rzędy 2-8, Kolumny 1-8) - Wężykiem
        for row in range(2, 9):
            columns = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            for col in columns:
                gcode.move_camera_to_grid(col=col, row=row)
                await asyncio.sleep(0.6)

                # Detekcja fizyczna
                detected_barcode = camera.decode_qr() or camera.recognize_pictogram()
                
                # Pobranie danych z bazy dla tego slotu
                db_item = db_map.get((row, col))
                db_barcode = db_item.product.barcode if db_item else None

                slot_status = {
                    "row": row,
                    "col": col,
                    "db_barcode": db_barcode,
                    "physical_barcode": detected_barcode,
                    "is_correct": True,
                    "error_message": None
                }

                # LOGIKA PORÓWNAWCZA
                if not detected_barcode and not db_barcode:
                    # Pusto tu i tu - OK
                    slot_status["error_message"] = "Puste"
                
                elif detected_barcode and not db_barcode:
                    # Jest na planszy, nie ma w bazie
                    slot_status["is_correct"] = False
                    slot_status["error_message"] = f"Nadmiar: Wykryto {detected_barcode}, brak w systemie"
                
                elif not detected_barcode and db_barcode:
                    # Jest w bazie, nie ma na planszy
                    slot_status["is_correct"] = False
                    slot_status["error_message"] = f"Brak: System widzi {db_barcode}, pole jest puste"
                
                elif detected_barcode != db_barcode:
                    # Inna figura na miejscu
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
        Przeprowadza pełną inwentaryzację 8x8 na drukarce PRINTER_3D.
        """
        # 1. Pobierz lub sprawdź regał PRINTER_3D
        result = await db.execute(select(Rack).where(Rack.designation == "PRINTER_3D"))
        rack = result.scalars().first()
        if not rack:
            logger.error("Regał PRINTER_3D nie istnieje w bazie!")
            return {"status": "error", "message": "Rack PRINTER_3D not found"}

        # Home drukarki przed startem
        gcode.home()

        # 2. Pętla inwentaryzacji (Wiersze 1-8, Kolumny 1-8)
        # Uwaga: w Twoim opisie rzędy 0-7 odpowiadają fizycznym 1-8
        for row in range(2, 9):
            # Optymalizacja trasy (snake pattern)
            # Jeśli wiersz jest parzysty, idź od 8 do 1, jeśli nieparzysty od 1 do 8
            columns = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            
            for col in columns:
                logger.info(f"Skanowanie pola: R{row} C{col}")
                
                # Ruch kamerą nad pole
                gcode.move_camera_to_grid(col=col, row=row)
                # Krótka pauza na stabilizację obrazu

                # Próba detekcji: QR -> Figura
                detected_barcode = camera.decode_qr()
                if not detected_barcode:
                    detected_barcode = camera.recognize_pictogram()

                if detected_barcode:
                    # ZNALEZIONO PRODUKT
                    await InventoryService._handle_found_item(
                        db, rack.id, row, col, detected_barcode, user_id
                    )

        await db.commit()
        return {"status": "success", "message": "Inwentaryzacja zakończona"}

    @staticmethod
    async def _handle_found_item(db: AsyncSession, rack_id: int, row: int, col: int, barcode: str, user_id: int):
        """Aktualizuje bazę, jeśli wykryto produkt."""
        # Pobierz definicję produktu po barcode (np. 'WC', 'HB')
        prod_result = await db.execute(
            select(ProductDefinition).where(ProductDefinition.barcode == barcode)
        )
        product = prod_result.scalars().first()
        
        if not product:
            logger.warning(f"Wykryto kod {barcode}, ale nie ma takiej definicji w bazie.")
            return

        # Sprawdź czy na tym miejscu już coś jest
        existing_stmt = select(StockItem).where(
            StockItem.rack_id == rack_id,
            StockItem.position_row == row,
            StockItem.position_col == col,
            StockItem.y_position == 0
        )
        existing_item = (await db.execute(existing_stmt)).scalars().first()

        if existing_item:
            if existing_item.product_id == product.id:
                # Produkt się zgadza, nic nie rób
                return
            else:
                # Inny produkt na tym miejscu - usuń stary
                await db.delete(existing_item)

        # Dodaj nowy StockItem (Inwentaryzacja fizyczna nadpisuje system)
        new_item = StockItem(
            product_id=product.id,
            rack_id=rack_id,
            position_row=row,
            position_col=col,
            y_position=0,
            received_by_id=user_id,
            expiry_date=datetime.now() # Możesz tu wyliczyć z expiry_days
        )
        db.add(new_item)
        logger.info(f"Zaktualizowano: {barcode} na R{row} C{col}")