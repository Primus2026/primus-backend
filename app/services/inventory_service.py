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
        for row in range(1, 9):
            # Optymalizacja trasy (snake pattern)
            # Jeśli wiersz jest parzysty, idź od 8 do 1, jeśli nieparzysty od 1 do 8
            columns = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            
            for col in columns:
                logger.info(f"Skanowanie pola: R{row} C{col}")
                
                # Ruch kamerą nad pole
                gcode.move_camera_to_grid(col=col, row=row)
                # Krótka pauza na stabilizację obrazu
                await asyncio.sleep(0.5)

                # Próba detekcji: QR -> Figura
                detected_barcode = camera.decode_qr()
                if not detected_barcode:
                    detected_barcode = camera.recognize_pictogram()

                if detected_barcode:
                    # ZNALEZIONO PRODUKT
                    await InventoryService._handle_found_item(
                        db, rack.id, row, col, detected_barcode, user_id
                    )
                else:
                    # PUSTE POLE
                    await InventoryService._handle_empty_slot(db, rack.id, row, col)

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

    @staticmethod
    async def _handle_empty_slot(db: AsyncSession, rack_id: int, row: int, col: int):
        """Usuwa przedmioty z bazy, jeśli pole fizycznie jest puste."""
        stmt = delete(StockItem).where(
            StockItem.rack_id == rack_id,
            StockItem.position_row == row,
            StockItem.position_col == col
        )
        result = await db.execute(stmt)
        if result.rowcount > 0:
            logger.info(f"Usunięto nieistniejący fizycznie przedmiot z R{row} C{col}")