import asyncio
import logging
from typing import List, Optional, Tuple
from app.services.gcode_service import gcode

logger = logging.getLogger("TIC_TAC_TOE")

class TicTacToeService:
    # Konfiguracja pól
    BOARD_START = (1, 1)  # Plansza 3x3 zaczyna się od R1 C1 do R3 C3
    O_STORAGE = [(col, 8) for col in range(1, 6)]  # Kółka: R8, C1-5
    X_STORAGE = [(col, 7) for col in range(1, 6)]  # Krzyżyki: R7, C1-5

    @staticmethod
    def check_winner(board: List[str]) -> Optional[str]:
        lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in lines:
            if board[a] and board[a] == board[b] == board[c]:
                return board[a]
        return "Draw" if all(board) else None

    @staticmethod
    def minimax(board: List[str], depth: int, is_maximizing: bool) -> int:
        res = TicTacToeService.check_winner(board)
        if res == 'X': return 10 - depth
        if res == 'O': return depth - 10
        if res == 'Draw': return 0

        if is_maximizing:
            best = -1000
            for i in range(9):
                if not board[i]:
                    board[i] = 'X'
                    best = max(best, TicTacToeService.minimax(board, depth + 1, False))
                    board[i] = ''
            return best
        else:
            best = 1000
            for i in range(9):
                if not board[i]:
                    board[i] = 'O'
                    best = min(best, TicTacToeService.minimax(board, depth + 1, True))
                    board[i] = ''
            return best

    @staticmethod
    async def move_physical_piece(piece_type: str, board_index: int, piece_count: int):
        """Fizycznie przenosi figurę z magazynu na planszę."""
        if not gcode.is_connected:
            gcode.connect()
            gcode.home()

        # Skąd bierzemy?
        source_list = TicTacToeService.X_STORAGE if piece_type == 'X' else TicTacToeService.O_STORAGE
        src_col, src_row = source_list[piece_count]

        # Gdzie kładziemy? (0-8 -> rzędy 1-3, kolumny 1-3)
        target_row = (board_index // 3) + 1
        target_col = (board_index % 3) + 1

        logger.info(f"Ruch {piece_type}: Z R{src_row}C{src_col} na R{target_row}C{target_col}")
        
        gcode.pick_from_grid(col=src_col, row=src_row, level="bottom")
        gcode.place_on_grid(col=target_col, row=target_row, level="bottom")

    @staticmethod
    async def cleanup_board(current_board: List[str]):
        """Odkłada figury na miejsce po zakończeniu gry."""
        x_count, o_count = 0, 0
        for i, piece in enumerate(current_board):
            if not piece: continue
            
            target_list = TicTacToeService.X_STORAGE if piece == 'X' else TicTacToeService.O_STORAGE
            idx = x_count if piece == 'X' else o_count
            dst_col, dst_row = target_list[idx]
            
            src_row = (i // 3) + 1
            src_col = (i % 3) + 1

            gcode.pick_from_grid(col=src_col, row=src_row, level="bottom")
            gcode.place_on_grid(col=dst_col, row=dst_row, level="bottom")
            
            if piece == 'X': 
                x_count += 1
            else: 
                o_count += 1