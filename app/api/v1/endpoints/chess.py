from fastapi import APIRouter, Depends
from app.core import deps
from app.database.models.user import User
# Zakładam, że logika ChessService znajduje się w app.services.chess_service
# Jeśli wkleiłeś ją do stock_service, zmień import na: from app.services.stock_service import ChessService
from app.services.chess_service import ChessService 
from app.services.logo_service import LogoService

router = APIRouter()


@router.post("/layout-logo")
async def layout_logo_endpoint():
    return await LogoService.layout_ozt_logo()
    
@router.post("/arrange", response_model=dict)
async def arrange_chess_board(
    current_user: User = Depends(deps.get_current_admin)
):
    """
    Skanuje rzędy 3-6 i układa figury w formacji szachowej na rzędach 1, 2, 7, 8.
    Wymaga uprawnień administratora.
    """
    return await ChessService.arrange_chess_board()