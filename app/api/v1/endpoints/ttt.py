from fastapi import APIRouter, HTTPException, Body
from app.services.tic_tac_toe_service import TicTacToeService
from pydantic import BaseModel
from typing import List

router = APIRouter()

class MoveRequest(BaseModel):
    board: List[str]  # ['X', 'O', '', ...]
    move_index: int
    piece_type: str   # 'X' lub 'O'
    x_count: int
    o_count: int

@router.post("/move")
async def make_move(req: MoveRequest):
    # 1. Fizyczny ruch
    await TicTacToeService.move_physical_piece(req.piece_type, req.move_index, 
                                               req.x_count if req.piece_type == 'X' else req.o_count)
    return {"status": "ok"}

@router.post("/ai-move")
async def ai_move(req: MoveRequest):
    # 1. Oblicz najlepszy ruch (AI to zawsze X)
    best_val = -1000
    best_move = -1
    board = req.board.copy()
    
    for i in range(9):
        if not board[i]:
            board[i] = 'X'
            move_val = TicTacToeService.minimax(board, 0, False)
            board[i] = ''
            if move_val > best_val:
                best_move = i
                best_val = move_val
    
    if best_move != -1:
        await TicTacToeService.move_physical_piece('X', best_move, req.x_count)
        return {"move_index": best_move}
    raise HTTPException(status_code=400, detail="Brak możliwych ruchów")

@router.post("/restart")
async def restart_game(board: List[str] = Body(...)):
    await TicTacToeService.cleanup_board(board)
    return {"status": "cleaned"}