from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.voice_service import VoiceService

router = APIRouter()

class VoiceCommandRequest(BaseModel):
    text: str

from app.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, HTTPException, Depends


@router.post("/", response_model=dict)
async def process_voice_command(
    command: VoiceCommandRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Przetworzenie komendy głosowej przez Ollama (Qwen2.5) i wykonanie wykrytej intencji.
    """
    if not command.text:
        raise HTTPException(status_code=400, detail="Command text cannot be empty")
        
    result = await VoiceService.process_command(command.text, db)
    
    if result.get("status") == "error":
        # We perform a "soft" error return so the frontend can display the message
        return result
        
    return result
