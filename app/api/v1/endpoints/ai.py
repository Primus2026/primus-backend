from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.core.deps import get_current_user, get_current_admin
from app.services.ai_service import AIService
from typing import Any, List
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select
from pydantic import BaseModel
import tempfile
import shutil
import os
from app.schemas.ai import (
    RecognitionResult,
    FeedbackResponse,
    TaskStatusResponse,
    TaskRequestResponse,
)
from app.database.models.user import User
from app.core.celery_worker import celery_app
from app.tasks.ai_tasks import predict_task, retrain_model_task
from app.core.config import settings
import uuid

router = APIRouter()


@router.post(
    "/recognize",
    response_model=TaskRequestResponse,
    summary="Rozpoznaj produkt ze zdjęcia",
    responses={400: {"description": "Plik musi być obrazem"}},
)
async def recognize_product(
    file: UploadFile = File(...), current_user: User = Depends(get_current_user)
):
    """
    Rozpoznanie produktu na podstawie przesłanego zdjęcia.
    
    Endpoint przyjmuje plik obrazu, zapisuje go bezpiecznie i koleikuie zadanie w tle
    do wykonania rozpoznawania obiektu przy użyciu skonfigurowanego modelu AI.
    
    Zwraca ID zadania, które można odpytywać o status i wyniki.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    from app.core.storage import storage
    
    # Upload to storage/temp
    filename = f"{uuid.uuid4()}.jpg"
    s3_key = f"temp/{filename}"
    
    content = await file.read()
    await storage.save(s3_key, content)

    # Send task with S3 key
    task = predict_task.delay(s3_key)

    return TaskRequestResponse(task_id=task.id)


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Prześlij feedback do treningu AI",
    responses={400: {"description": "Plik musi być obrazem"}},
)
async def submit_feedback(
    product_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),  # Require Auth for feedback
):
    """
    Przesłanie zdjęcia feedbackowego dla konkretnego produktu.
    
    Umożliwia zalogowanym użytkownikom przesłanie poprawnych zdjęć dla danego ID produktu.
    Zdjęcia te są przechowywane i wykorzystywane do przyszłego douczania modelu.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    content = await file.read()
    await AIService.save_feedback(content, product_id)

    return FeedbackResponse(success=True, message="Feedback saved successfully")


@router.get("/retrain", response_model=TaskRequestResponse, summary="Dotrenuj model AI")
async def retrain_model(
    db: AsyncSession = Depends(get_db), current_user: Any = Depends(get_current_admin)
):
    """
    Uruchomienie procesu dotrenowania modelu AI.
    
    Inicjuje zadanie w tle (Celery), które dotrenowuje model używając
    zgromadzonych danych feedbackowych i treningowych. Operacja tylko dla Administratora.
    """

    task = retrain_model_task.delay()

    return TaskRequestResponse(task_id=task.id)


@router.post("/model/reset", summary="Zresetuj model AI")
async def reset_model(
    db: AsyncSession = Depends(get_db), current_user: Any = Depends(get_current_admin)
):
    """
    Reset modelu AI.
    
    Usuwa zcache'owane pliki modelu i restartuje serwis. Używane np. przy zmianie sprzętu (CPU/GPU)
    wymuszając ponowne pobranie/inicjalizację modelu.
    """
    AIService.reset_model()
    return {
        "message": "Model reset successfully. It will be re-initialized on the next request."
    }


@router.post(
    "/training-data/{product_id}",
    response_model=FeedbackResponse,
    summary="Prześlij dane treningowe",
)
async def post_training_data(
    files: List[UploadFile],
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin),
):
    """
    Masowe przesyłanie danych treningowych dla produktu.
    
    Umożliwia administratorom przesłanie wielu zdjęć treningowych dla konkretnego produktu na raz.
    Zdjęcia są dodawane do zbioru danych do retreningu. Operacja tylko dla Administratora.
    """
    await AIService.bulk_save_training_data(files, product_id)

    return FeedbackResponse(success=True, message="Training data saved successfully")


@router.get(
    "/task-status/{task_id}",
    response_model=TaskStatusResponse,
    summary="Pobierz status zadania",
    responses={404: {"description": "Zadanie nie znalezione"}},
)
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Sprawdzenie statusu zadania w tle.
    
    Pobiera obecny stan (PENDING, STARTED, SUCCESS, FAILURE) oraz wynik
    konkretnego zadania Celery (np. treningu lub predykcji) na podstawie ID.
    """

    task = celery_app.AsyncResult(task_id)

    result = task.result
    if task.state == "FAILURE":
        result = {"error": str(result)}

    return TaskStatusResponse(task_id=task.id, status=task.state, result=result)
