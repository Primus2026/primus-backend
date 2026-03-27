import asyncio
import logging
from fastapi import HTTPException
from app.services.camera_service import camera
from app.services.gcode_service import gcode

logger = logging.getLogger("LOGO_SERVICE")

class LogoService:
    # Definicja wzoru Logo OZT (21 pól)
    LOGO_PATTERN = [
        (1,1), (2,1), (3,1),
        (1,2), (3,2),
        (1,3), (2,3), (3,3), (4,3), (5,3), (6,3),
        (5,4),
        (4,5),
        (3,6), (4,6), (5,6), (6,6), (7,6), (8,6),
        (7,7),
        (7,8)
    ]

    @staticmethod
    async def layout_ozt_logo():
        # Zapewnienie połączenia
        if not gcode.is_connected:
            gcode.connect()
            gcode.home()

        # 1. Pełne skanowanie planszy 8x8 wężykiem
        found_blocks = []
        logger.info("Skanowanie planszy w poszukiwaniu figur...")

        for row in range(1, 9):
            cols = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            for col in cols:
                gcode.move_camera_to_grid(col=col, row=row)
                await asyncio.sleep(0.1) # Optymalizacja czasu
                
                if camera.decode_qr() or camera.recognize_pictogram():
                    found_blocks.append((col, row))
        
        count = len(found_blocks)
        required = len(LogoService.LOGO_PATTERN)

        # 2. Walidacja liczby figur
        if count < required:
            raise HTTPException(
                status_code=400, 
                detail=f"Niewystarczająca liczba figur! Znaleziono {count}, a wymagane jest dokładnie {required}. Dołóż jeszcze {required - count}."
            )
        
        if count > required:
            raise HTTPException(
                status_code=400, 
                detail=f"Za dużo figur na planszy! Znaleziono {count}, a logo wymaga tylko {required}. Usuń {count - required} nadmiarowe elementy."
            )

        # 3. Jeśli liczba jest idealna (21), przechodzimy do układania
        # Wykluczamy klocki, które już stoją poprawnie
        targets_to_fill = [t for t in LogoService.LOGO_PATTERN if t not in found_blocks]
        available_blocks = [b for b in found_blocks if b not in LogoService.LOGO_PATTERN]

        moved_count = 0
        for target in targets_to_fill:
            t_col, t_row = target
            # Algorytm najbliższego sąsiada
            closest_block = min(available_blocks, key=lambda b: (b[0]-t_col)**2 + (b[1]-t_row)**2)
            b_col, b_row = closest_block

            try:
                gcode.pick_from_grid(col=b_col, row=b_row, level="bottom")
                gcode.place_on_grid(col=t_col, row=t_row, level="bottom")
                
                available_blocks.remove(closest_block)
                moved_count += 1
            except Exception as e:
                logger.error(f"G-Code error: {e}")
                raise HTTPException(status_code=500, detail="Błąd mechaniczny podczas układania logo.")

        return {
            "status": "success", 
            "message": f"LOGO OZT ułożone pomyślnie! Przesunięto {moved_count} figur.",
        }