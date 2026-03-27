import asyncio
import logging
import json
import httpx
from typing import List, Optional
from app.services.gcode_service import gcode
from app.core.config import settings

logger = logging.getLogger("TIC_TAC_TOE")

class TicTacToeService:
    # Konfiguracja pól
    O_STORAGE = [(col, 8) for col in range(1, 6)]  # Kółka (SI): R8, C1-5
    X_STORAGE = [(col, 7) for col in range(1, 6)]  # Krzyżyki (Gracz): R7, C1-5

    @staticmethod
    def get_ai_prompt(board: List[str]) -> str:
        board_str = ",".join([s if s else "." for s in board])
        return f"""
You are an expert Tic-Tac-Toe AI. Your symbol is 'O'. The opponent is 'X'.
Your task: Analyze the board state and return the index (0-8) of your next best move.

BOARD LAYOUT (Indices):
0 | 1 | 2
---------
3 | 4 | 5
---------
6 | 7 | 8

CURRENT BOARD STATE:
{board_str}
(where '.' is empty, 'X' is player, 'O' is you)

STRATEGY:
1. If you can win in one move, take it.
2. If the opponent is about to win, block them.
3. Otherwise, take the best streategy for you . 

EXAMPLES:
Board: X,X,.,O,.,.,.,.,. -> Response: {{"move_index": 2}} (Blocking X)
Board: O,O,.,X,.,X,.,.,. -> Response: {{"move_index": 2}} (Winning move)
Board: .,.,.,.,.,.,.,.,. -> Response: {{"move_index": 4}} (Taking center)

OUTPUT FORMAT:
Strict JSON only. No text, no markdown.
Example: {{"move_index": 4}}
"""

    @staticmethod
    async def get_ai_move_llm(board: List[str]) -> int:
        """Komunikuje się z Ollama/Qwen, aby uzyskać ruch SI."""
        prompt = TicTacToeService.get_ai_prompt(board)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    settings.OLLAMA_URL,
                    json={
                        "model": settings.VOICE_LLM_MODEL, # Używamy quena z projektu
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                response.raise_for_status()
                res_json = response.json()
                data = json.loads(res_json.get("response", "{}"))
                
                move = data.get("move_index")
                if move is not None and 0 <= move <= 8 and board[move] == "":
                    return move
                
                # Fallback: pierwszy wolny slot jeśli LLM zawiedzie
                return board.index("")
        except Exception as e:
            logger.error(f"LLM AI Move failed: {e}")
            return board.index("")

    @staticmethod
    async def move_physical_piece(piece_type: str, board_index: int, piece_count: int):

        source_list = TicTacToeService.X_STORAGE if piece_type == 'X' else TicTacToeService.O_STORAGE
        # piece_count to liczba figur danego typu już będących na planszy (0-4)
        src_col, src_row = source_list[piece_count]

        # Mapowanie 0-8 na siatkę 1-3
        target_row = (board_index // 3) + 1
        target_col = (board_index % 3) + 1

        logger.info(f"Fizyczny ruch {piece_type}: Z R{src_row}C{src_col} na planszę R{target_row}C{target_col}")
        
        gcode.pick_from_grid(col=src_col, row=src_row, level="bottom")
        gcode.place_on_grid(col=target_col, row=target_row, level="bottom")

    @staticmethod
    async def cleanup_board(current_board: List[str]):
        """Odkłada figury na miejsce."""
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
            
            if piece == 'X': x_count += 1
            else: o_count += 1

        gcode.home()

    @staticmethod
    def check_winner(board: List[str]) -> Optional[str]:
        lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in lines:
            if board[a] and board[a] == board[b] == board[c]:
                return board[a]
        return "DRAW" if all(board) else None