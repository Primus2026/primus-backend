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
    # SI (O) prosi LLM (Ollama/Qwen) o wyznaczenie najlepszego ruchu
    try:
        best_move = await TicTacToeService.get_ai_move_llm(req.board)
        
        if best_move != -1 and not req.board[best_move]:
            # SI zawsze kładzie 'O' (pobierane z R8)
            await TicTacToeService.move_physical_piece('O', best_move, req.o_count)
            return {"move_index": best_move}
            
        raise HTTPException(status_code=400, detail="SI zwróciła zajęte pole lub błąd")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/restart")
async def restart_game(board: List[str] = Body(...)):
    await TicTacToeService.cleanup_board(board)
    return {"status": "cleaned"}