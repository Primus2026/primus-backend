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
    summary="Recognize product from image",
    responses={400: {"description": "File must be an image"}},
)
async def recognize_product(
    file: UploadFile = File(...), current_user: User = Depends(get_current_user)
):
    """
    Recognize a product from an uploaded image.

    This endpoint accepts an image file, saves it securely, and queues a background task
    to perform object recognition using the configured AI model.

    Returns a task ID which can be polled for status and results.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)

    filename = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join(temp_dir, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Send task
    task = predict_task.delay(file_path)

    return TaskRequestResponse(task_id=task.id)


@router.post(
    "/feedback",
    response_model=TaskRequestResponse,
    summary="Submit feedback for AI training",
    responses={400: {"description": "File must be an image"}},
)
async def submit_feedback(
    product_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),  # Require Auth for feedback
):
    """
    Submit feedback image for a specific product.

    This endpoint allows authenticated users to upload correct images for a product ID.
    These images are stored and used for future model retraining to improve accuracy.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    content = await file.read()
    AIService.save_feedback(content, product_id)

    return FeedbackResponse(success=True, message="Feedback saved successfully")


@router.get("/retrain", response_model=TaskRequestResponse, summary="Retrain AI model")
async def retrain_model(
    db: AsyncSession = Depends(get_db), current_user: Any = Depends(get_current_admin)
):
    """
    Trigger the AI model retraining process.

    This endpoint initiates a background Celery task to retrain the AI model using
    all accumulated feedback and training data. This is an admin-only operation.
    """

    task = retrain_model_task.delay()

    return TaskRequestResponse(task_id=task.id)


@router.post("/model/reset", summary="Reset AI Model")
async def reset_model(
    db: AsyncSession = Depends(get_db), current_user: Any = Depends(get_current_admin)
):
    """
    Reset the AI model.

    This endpoint deletes cached model files and resets the service. Use this when switching hardware (CPU/GPU) to force a fresh model download.
    """
    AIService.reset_model()
    return {
        "message": "Model reset successfully. It will be re-initialized on the next request."
    }


@router.post(
    "/training-data/{product_id}",
    response_model=FeedbackResponse,
    summary="Upload training data",
)
async def post_training_data(
    files: List[UploadFile],
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin),
):
    """
    Bulk upload training data for a product.

    Allows administrators to upload multiple training images for a specific product ID
    at once. These images are added to the dataset for retraining. This is an admin-only operation.
    """
    await AIService.bulk_save_training_data(files, product_id)

    return FeedbackResponse(success=True, message="Training data saved successfully")


@router.get(
    "/task-status/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get retrain status",
    responses={404: {"description": "Task not found"}},
)
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin),
):
    """
    Check the status of a background task.

    Retrieves the current state (PENDING, STARTED, SUCCESS, FAILURE) and result
    of a specific Celery task (e.g., retraining or prediction) given its ID.
    """

    task = celery_app.AsyncResult(task_id)

    result = task.result
    if task.state == "FAILURE":
        result = {"error": str(result)}

    return TaskStatusResponse(task_id=task.id, status=task.state, result=result)
