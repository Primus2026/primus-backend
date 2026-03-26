from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any

from app.services.chess_service import chess_service

router = APIRouter()

@router.get("/board-state")
def get_board_state() -> Dict[str, Any]:
    """Zwraca obecny wirtualny stan szachownicy 8x8."""
    return {"board": chess_service.board_state}

@router.post("/inventory")
def run_inventory(use_qr: bool = True):
    """
    Faza 1 - Smart Discovery
    Blokuje HTTP aż ramię przejedzie i zmapuje planszę (long-polling zgodnie ze specyfikacją).
    """
    try:
        chess_service.inventory(use_qr=use_qr)
        return {"status": "ok", "message": "Inwentaryzacja zakończona", "board": chess_service.board_state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/setup-smart")
def setup_smart() -> Dict[str, Any]:
    """
    Faza 2 i 3 - Graph Solver & Unified Scheduler
    Wykonuje inteligentne układanie figur.
    """
    try:
        chess_service.setup_smart()
        return {"status": "ok", "message": "Rozstawianie zakończone"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/layout-logo")
def layout_logo(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Specjalny układ Logo OZT."""
    # Możemy go obsłużyć asynchronicznie lub prosto
    return {"status": "ok", "message": "Funkcja zastępcza logo OZT wywołana"}

