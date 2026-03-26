import asyncio
import logging
from typing import List, Dict, Tuple
from app.services.camera_service import camera
from app.services.gcode_service import gcode

logger = logging.getLogger("CHESS_SERVICE")

class ChessService:
    # Definicja docelowych pozycji dla szachownicy
    CHESS_TARGETS = {
        # Rząd 1: Białe figury
        "WB": [(1,1), (8,1)], "SB": [(2,1), (7,1)], "GB": [(3,1), (6,1)], "HB": [(4,1)], "KB": [(5,1)],
        # Rząd 2: Białe pionki
        "PB": [(i, 2) for i in range(1, 9)],
        # Rząd 7: Czarne pionki
        "PC": [(i, 7) for i in range(1, 9)],
        # Rząd 8: Czarne figury
        "WC": [(1,8), (8,8)], "SC": [(2,8), (7,8)], "GC": [(3,8), (6,8)], "HC": [(4,8)], "KC": [(5,8)],
    }

    @staticmethod
    async def arrange_chess_board():
        """Główna funkcja skanowania i układania figur."""
        
        # 1. Zapewnienie połączenia
        if not gcode.is_connected:
            gcode.connect()
            gcode.home()

        # 2. SKANOWANIE (Rzędy 3, 4, 5, 6) - Wężykiem
        found_pieces: List[Dict] = []
        logger.info("Rozpoczynam skanowanie rzędów 3-6...")

        for row in range(3, 7):
            # Wężyk: nieparzyste 1->8, parzyste 8->1
            cols = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            
            for col in cols:
                gcode.move_camera_to_grid(col=col, row=row)
                await asyncio.sleep(0.6) # Czas na focus kamery

                barcode = camera.decode_qr()
                if not barcode:
                    barcode = camera.recognize_pictogram()

                if barcode:
                    logger.info(f"Znaleziono figurę {barcode} na R{row} C{col}")
                    found_pieces.append({
                        "type": barcode,
                        "current_pos": (col, row)
                    })

        if not found_pieces:
            return {"status": "error", "message": "Nie znaleziono żadnych figur na polach 3-6"}

        # 3. OPTYMALIZACJA I UKŁADANIE
        # Kopiujemy cele, żeby móc je "wykreślać"
        available_targets = {k: v.copy() for k, v in ChessService.CHESS_TARGETS.items()}
        
        # Sortujemy znalezione figury tak, aby najpierw układać te, 
        # które mają najbliżej do swoich rzędów docelowych (opcjonalnie)
        
        for piece in found_pieces:
            p_type = piece["type"]
            curr_col, curr_row = piece["current_pos"]
            
            if p_type in available_targets and available_targets[p_type]:
                # Znajdź najbliższy cel dla tej konkretnej figury (Euklidesowo)
                targets = available_targets[p_type]
                best_target = min(targets, key=lambda t: (t[0]-curr_col)**2 + (t[1]-curr_row)**2)
                
                target_col, target_row = best_target
                
                logger.info(f"Ruch: {p_type} z ({curr_col},{curr_row}) do ({target_col},{target_row})")
                
                # FIZYCZNY RUCH
                try:
                    # Podnieś z obecnej pozycji (level 0, bo zakładamy jedną warstwę)
                    gcode.pick_from_grid(col=curr_col, row=curr_row, level=0)
                    # Odłóż na docelową pozycję
                    gcode.place_on_grid(col=target_col, row=target_row, level=0)
                except Exception as e:
                    logger.error(f"Błąd G-Code: {e}")
                    continue

                # Usuń wykorzystany cel
                targets.remove(best_target)
            else:
                logger.warning(f"Figura {p_type} nie ma zdefiniowanego celu lub wszystkie miejsca zajęte.")

        return {"status": "success", "message": "Szachy ułożone", "pieces_moved": len(found_pieces)}