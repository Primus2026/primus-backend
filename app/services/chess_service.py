import logging
import math
from typing import List, Dict, Optional, Tuple

from app.services.gcode_service import gcode
from app.services.camera_service import camera

logger = logging.getLogger("ChessService")

class ChessService:
    """Implementacja algorytmu rozstawiania figur szachowych zgodnie z chess_algo_doc.docx."""

    def __init__(self):
        # 64 elementowa tablica z aktualnym stanem szachownicy (z Phase 1)
        # null - puste, string np. "WP" - zajęte
        self.board_state = [None] * 64

        # Mapowanie docelowego układu szachownicy (wariant standardowy):
        self.target_board = [
            "BR", "BN", "BB", "BQ", "BK", "BB", "BN", "BR",
            "BP", "BP", "BP", "BP", "BP", "BP", "BP", "BP",
            None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None,
            "WP", "WP", "WP", "WP", "WP", "WP", "WP", "WP",
            "WR", "WN", "WB", "WQ", "WK", "WB", "WN", "WR"
        ]

    def _index_to_pos(self, index: int) -> Tuple[int, int]:
        """Konwertuje indeks (0-63) na kolumnę i wiersz (1-8)."""
        col = (index % 8) + 1
        row = (index // 8) + 1
        return col, row

    def _pos_to_index(self, col: int, row: int) -> int:
        """Konwertuje kolumnę i wiersz (1-8) na indeks (0-63)."""
        return ((row - 1) * 8) + (col - 1)

    def _dist(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Odległość Euklidesowa między polami 1-8."""
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def _cells_on_path(self, col1: int, row1: int, col2: int, row2: int) -> List[Tuple[int, int]]:
        """Zwraca listę pól przecinanych przez odcinek (bez pola początkowego i końcowego) (Bresenham)."""
        def sign(i):
            return 1 if i > 0 else -1 if i < 0 else 0

        dx, dy = abs(col2 - col1), abs(row2 - row1)
        sx, sy = sign(col2 - col1), sign(row2 - row1)
        err = dx - dy
        x, y = col1, row1
        cells = []
        while (x, y) != (col2, row2):
            cells.append((x, y))
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        # Usuwamy punkt początkowy
        if cells and cells[0] == (col1, row1):
            cells.pop(0)
        return cells

    def inventory(self, use_qr: bool = True):
        """
        Faza 1 - Smart Discovery.
        """
        logger.info("Rozpoczynam Inwentaryzację - Faza 1: Smart Discovery")
        self.board_state = [None] * 64
        
        # Wężyk: od row=1 col=1 do col=8, potem row=2 col=8 do col=1 itd.
        snake_path = []
        for row in range(1, 9):
            cols = range(1, 9) if row % 2 != 0 else range(8, 0, -1)
            for col in cols:
                snake_path.append((col, row))
                
        # Start scanning
        scans_found = 0
        for col, row in snake_path:
            gcode.move_to_grid(col, row)
            # Faza 3.1 kompensacja wibracji -> pauza 200ms przez sleep, choć lepiej w gcode (G4 P200)
            gcode.send_command("G4 P200")
            
            piece = None
            if use_qr:
                piece = camera.decode_qr()
                if not piece:
                    # Retry policy 
                    gcode.jog(dx=2.0)
                    gcode.send_command("G4 P200")
                    piece = camera.decode_qr()
            else:
                piece = camera.recognize_pictogram()
                if not piece:
                    gcode.jog(dx=2.0)
                    gcode.send_command("G4 P200")
                    piece = camera.recognize_pictogram()

            idx = self._pos_to_index(col, row)
            if piece:
                logger.info(f"Znaleziono figurę {piece} na polu col={col}, row={row}")
                self.board_state[idx] = piece
                scans_found += 1
            
            # Wg dokumentacji "early-abort po N znaleziskach" - my zakładamy maks 32 figury
            if scans_found >= 32:
                break

    def setup_smart(self):
        """
        Faza 2 i 3 - Graph Solver i Unified Scheduler.
        Wymaga żeby self.board_state zostało wypełnione.
        """
        logger.info("Rozpoczynam Setup Smart (Graph Solver + Unified Scheduler)")
        
        # 1. Klasyfikacja relacji
        locked_positions = set()
        moves_needed = [] # Lista (from_idx, to_idx, piece)

        # Znajdź pozycje figurek
        pieces_positions = {}
        for idx, piece in enumerate(self.board_state):
            if piece:
                if piece not in pieces_positions:
                    pieces_positions[piece] = []
                pieces_positions[piece].append(idx)
        
        # Odtwórz cele
        target_board_temp = list(self.target_board)
        virtual_board = list(self.board_state)

        # Znajdź najpierw LOCKED: te które już są na swoim miejscu
        for idx, t_piece in enumerate(target_board_temp):
            if t_piece and self.board_state[idx] == t_piece:
                locked_positions.add(idx)
                # Oznacz by ich nie używać
                pieces_positions[t_piece].remove(idx)
                target_board_temp[idx] = None
                
        # Teraz dopasuj startowiska pozostałych
        for to_idx, t_piece in enumerate(target_board_temp):
            if t_piece:
                if not pieces_positions.get(t_piece):
                    logger.warning(f"Brak figury {t_piece} do umieszczenia na indeksie {to_idx}")
                    continue
                # Weź pierwszą z brzegu figurkę tego typu
                from_idx = pieces_positions[t_piece].pop(0)
                moves_needed.append({'from': from_idx, 'to': to_idx, 'piece': t_piece})

        # Wyznaczenie zależności - kto kogo blokuje
        # chain / cycle resolver
        moves_queue = []
        
        def is_empty(idx, board):
            return board[idx] is None

        # Prosty resolver cyklowy z grafem i Nearest Neighbor optymalizacją (Zwiększa Szybkość Rozstawiania)
        # Głowa robota zaczyna na środku lub po ostatnim ruchu.
        curr_gcode_pos = (4.5, 4.5)

        while moves_needed:
            # Szukamy ruchu, którego cel jest pusty (Ścieżka prosta lub koniec łańcucha)
            ready_moves = [m for m in moves_needed if is_empty(m['to'], virtual_board)]
            
            if ready_moves:
                # Szeregowanie zachłanne (Nearest Neighbor wg dist(curr_pos -> P_PICK))
                best_move = None
                best_move_dist = float('inf')
                
                for rm in ready_moves:
                    rm_col, rm_row = self._index_to_pos(rm['from'])
                    d = self._dist(curr_gcode_pos, (rm_col, rm_row))
                    if d < best_move_dist:
                        best_move_dist = d
                        best_move = rm
                        
                move = best_move
                moves_needed.remove(move)
                moves_queue.append(move)
                
                # Aktualizuj virtual board
                virtual_board[move['to']] = move['piece']
                virtual_board[move['from']] = None
                
                # Aktualizuj pozycję głowicy po tym ruchu na miejsce odłożenia 'to'
                to_c, to_r = self._index_to_pos(move['to'])
                curr_gcode_pos = (to_c, to_r)
            else:
                # Mamy cykl! Wybieramy pierwszy ruch z brzegu jako początek przerwania cyklu
                # (Zgodnie z Nearest Neighbor można wybrać cykl najbliższy, ale tu jest rzadka kolizja)
                cyc_move = moves_needed[0]
                P1_idx = cyc_move['from']
                
                # Znajdź bufor (puste pole) minimalizujące dist(P_PICK -> B) + dist(B -> P_DROP)
                best_buffer = None
                best_dist = float('inf')
                col1, row1 = self._index_to_pos(P1_idx)
                colD, rowD = self._index_to_pos(cyc_move['to'])  # P_n
                
                for i in range(64):
                    if is_empty(i, virtual_board):
                        colB, rowB = self._index_to_pos(i)
                        
                        d1 = self._dist((col1, row1), (colB, rowB))   # PICK do BUFOR
                        d2 = self._dist((colB, rowB), (colD, rowD))   # BUFOR do cel
                        # Opcjonalnie dodać dystans maszyny do P1
                        d_total = d1 + d2 + self._dist(curr_gcode_pos, (col1, row1))
                        
                        if d_total < best_dist:
                            best_dist = d_total
                            best_buffer = i
                            
                if best_buffer is None:
                    raise RuntimeError("Brak miejsca na bufor! Plansza jest pełna.")

                # Tymczasowy ruch do bufora
                buffer_move = {'from': P1_idx, 'to': best_buffer, 'piece': cyc_move['piece']}
                moves_queue.append(buffer_move)
                
                virtual_board[best_buffer] = cyc_move['piece']
                virtual_board[P1_idx] = None
                
                # Aktualizuj pozycję głowicy na bufor
                b_c, b_r = self._index_to_pos(best_buffer)
                curr_gcode_pos = (b_c, b_r)
                
                # Aktualizuj cyc_move - nie zaczyna się już z P1_idx ale na buforze
                cyc_move['from'] = best_buffer

        # Otrzymaliśmy moves_queue z atomowymi ruchami.
        # Możemy odpalić 2-opt optymalizację tutaj, ale pominiemy to na rzecz stabilności dla turnieju (NN starczy lub kolejność łańcuchowa).
        
        # Odtwarzanie ruchów z schedulerem (Phase 3.3 Bresenham Z-hop)
        # Z = 4 mm - wszystkie pola puste
        # Z = 8 mm - coś na ścieżce
        curr_gcode_board = list(self.board_state)
        
        for move in moves_queue:
            from_col, from_row = self._index_to_pos(move['from'])
            to_col, to_row = self._index_to_pos(move['to'])

            # Wyznacz Z-hop na podstawie Bresenhama
            path_cells = self._cells_on_path(from_col, from_row, to_col, to_row)
            z_hop = 4.0
            for cx, cy in path_cells:
                c_idx = self._pos_to_index(cx, cy)
                if curr_gcode_board[c_idx] is not None:
                    z_hop = 8.0
                    break
            
            # Bezpośrednio przed elektromagnesem M400
            gcode.send_command("M400")
            
            # Pick
            # Możemy dostosować Z_SAFE czasowo do z_hop
            old_z_safe = gcode.Z_SAFE
            gcode.Z_SAFE = z_hop
            
            try:
                gcode.pick_from_grid(from_col, from_row)
                gcode.send_command("M400")
                gcode.place_on_grid(to_col, to_row)
            finally:
                gcode.Z_SAFE = old_z_safe
                
            # Aktualizacja lokalna
            curr_gcode_board[move['to']] = move['piece']
            curr_gcode_board[move['from']] = None

        self.board_state = list(curr_gcode_board)
        logger.info("Zakończono rozstawianie szachów.")
        
chess_service = ChessService()
