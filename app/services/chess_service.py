import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from app.services.camera_service import camera
from app.services.gcode_service import gcode

logger = logging.getLogger("CHESS_SERVICE")

class ChessService:
    # Definicja pozycji startowych dla każdego typu figury
    # Tutaj użytkownik kładzie figury przed uruchomieniem algorytmu
    STARTING_POSITIONS = {
        "WB": [(1,1), (8,1)], "SB": [(2,1), (7,1)], "GB": [(3,1), (6,1)], "HB": [(4,1)], "KB": [(5,1)],
        "PB": [(i, 2) for i in range(1, 9)],
        "PC": [(i, 7) for i in range(1, 9)],
        "WC": [(1,8), (8,8)], "SC": [(2,8), (7,8)], "GC": [(3,8), (6,8)], "HC": [(4,8)], "KC": [(5,8)],
    }

    @staticmethod
    async def set_custom_formation(requested_pieces: List[Dict]):
        """
        Inteligentne układanie figur z pozycji startowych na docelowe.
        
        requested_pieces: list of {"type": "WB", "col": 4, "row": 5}
        
        Algorytm:
        1. Zbierz unikalne typy figur z żądania
        2. Dla każdego typu, skanuj TYLKO jego potencjalne pozycje startowe
        3. Przesuwaj znalezione figury na docelowe pozycje
        """
        if not gcode.is_connected:
            gcode.connect()
            gcode.home()

        # 1. Zbierz typy figur i ile sztuk każdego typu potrzebujemy
        needed_pieces: Dict[str, List[Tuple[int, int]]] = {}  # typ -> lista docelowych (col, row)
        for req in requested_pieces:
            p_type = req["type"]
            target = (req["col"], req["row"])
            if p_type not in needed_pieces:
                needed_pieces[p_type] = []
            needed_pieces[p_type].append(target)

        logger.info(f"Potrzebne figury: {needed_pieces}")

        # 2. Skanuj tylko pozycje startowe dla potrzebnych typów i znajdź figury
        found_pieces: Dict[str, List[Tuple[int, int]]] = {}  # typ -> lista znalezionych (col, row)
        
        # Zbierz wszystkie pozycje do przeskanowania (bez duplikatów)
        positions_to_scan: List[Tuple[int, int, str]] = []  # (col, row, expected_type)
        for p_type in needed_pieces.keys():
            if p_type in ChessService.STARTING_POSITIONS:
                for pos in ChessService.STARTING_POSITIONS[p_type]:
                    positions_to_scan.append((pos[0], pos[1], p_type))
        
        # Sortuj pozycje wężykiem dla optymalnego ruchu
        positions_to_scan.sort(key=lambda p: (p[1], p[0] if p[1] % 2 == 1 else -p[0]))
        
        logger.info(f"Skanowanie {len(positions_to_scan)} potencjalnych pozycji...")
        
        for col, row, expected_type in positions_to_scan:
            gcode.move_camera_to_grid(col=col, row=row)
            await asyncio.sleep(0.5)  # Czas na stabilizację
            
            # Rozpoznaj figurę
            detected = camera.decode_qr()
            if not detected:
                detected = camera.recognize_pictogram()
            
            if detected:
                logger.info(f"Znaleziono {detected} na ({col},{row}), oczekiwano {expected_type}")
                # Zapisz tylko jeśli to oczekiwany typ (lub akceptujemy wszystko)
                if detected not in found_pieces:
                    found_pieces[detected] = []
                found_pieces[detected].append((col, row))

        logger.info(f"Znalezione figury: {found_pieces}")

        # 3. Przesuń figury na docelowe pozycje
        moved_count = 0
        errors = []

        for p_type, targets in needed_pieces.items():
            sources = found_pieces.get(p_type, []).copy()
            
            if len(sources) < len(targets):
                errors.append(f"Brak wystarczającej liczby figur {p_type}: znaleziono {len(sources)}, potrzeba {len(targets)}")
                continue
            
            for target in targets:
                t_col, t_row = target
                
                # Znajdź najbliższą figurę tego typu
                if not sources:
                    break
                    
                best_source = min(sources, key=lambda s: (s[0]-t_col)**2 + (s[1]-t_row)**2)
                s_col, s_row = best_source
                
                # Jeśli figura już stoi na miejscu docelowym, pomiń
                if s_col == t_col and s_row == t_row:
                    logger.info(f"{p_type} już na miejscu ({t_col},{t_row})")
                    sources.remove(best_source)
                    continue
                
                try:
                    logger.info(f"Przesuwam {p_type} z ({s_col},{s_row}) na ({t_col},{t_row})")
                    gcode.pick_from_grid(col=s_col, row=s_row, level="bottom")
                    gcode.place_on_grid(col=t_col, row=t_row, level="bottom")
                    
                    sources.remove(best_source)
                    moved_count += 1
                except Exception as e:
                    logger.error(f"Błąd G-Code: {e}")
                    errors.append(f"Błąd ruchu {p_type}: {e}")

        result = {
            "status": "success" if not errors else "partial",
            "moved": moved_count,
            "requested": len(requested_pieces)
        }
        if errors:
            result["errors"] = errors
            
        return result
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
                await asyncio.sleep(1.0)  # Zwiększone z 0.6s - więcej czasu na stabilizację kamery po ruchu

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
                    # Podnieś z obecnej pozycji (level="bottom", bo zakładamy jedną warstwę)
                    gcode.pick_from_grid(col=curr_col, row=curr_row, level="bottom")
                    # Odłóż na docelową pozycję
                    gcode.place_on_grid(col=target_col, row=target_row, level="bottom")
                except Exception as e:
                    logger.error(f"Błąd G-Code: {e}")
                    continue

                # Usuń wykorzystany cel
                targets.remove(best_target)
            else:
                logger.warning(f"Figura {p_type} nie ma zdefiniowanego celu lub wszystkie miejsca zajęte.")

        return {"status": "success", "message": "Szachy ułożone", "pieces_moved": len(found_pieces)}