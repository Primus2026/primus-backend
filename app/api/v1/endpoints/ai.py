from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.api.v1.core.dependencies import get_current_user
from app.services.ai_service import AIService #not implemented yet
from typing import Any
from app.database.models.product_definition import ProductDefinition
from sqlalchemy import select
from pydantic import BaseModel
import tempfile
import shutil
import os
from app.schemas.ai import RecognitionResult, FeedbackResponse
from app.database.models.user import User

router = APIRouter()

@router.post("/recognize", response_model=RecognitionResult, summary="Recognize product from image", responses={
    400: {"description": "File must be an image"}
})
async def recognize_product(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user) 
) -> Any:
    """
    Recognize a product from an uploaded image using YOLOv8.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")


    
    # Save uploaded file to temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        product_id, confidence = await AIService.predict(tmp_path)
    finally:
        os.remove(tmp_path)
    
    if product_id == -1: # if unknown product
        return RecognitionResult(product_id=-1, confidence=0.0, name="Unknown")
        
    # Fetch product name
    result = await db.execute(select(ProductDefinition).where(ProductDefinition.id == product_id))
    product = result.scalars().first()
    
    
    raise HTTPException(status_code=405, detail="Not implemented")

    return RecognitionResult(
        product_id=product_id,
        confidence=confidence,
        name=product.name
    )

@router.post("/feedback", response_model=FeedbackResponse, summary="Submit feedback for AI training")
async def submit_feedback(
    product_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user) # Require Auth for feedback
) -> Any:
    """
    Submit a corrected/verified image for a product.
    This image will be used to retrain the model.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
        
    content = await file.read()
    await AIService.save_feedback(content, product_id)
    
    raise HTTPException(status_code=405, detail="Not implemented")

@router.get("/retrain", response_model=FeedbackResponse, summary="Retrain AI model")
async def retrain_model(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin)
) -> Any:
    """
    Retrain the AI model using all feedback images.
    """
    await AIService.retrain_model() # to be implemented, force retrain without waiting for scheduled task
    
    raise HTTPException(status_code=405, detail="Not implemented")

@router.get("/training-data", response_model=FeedbackResponse, summary="Get training data")
async def get_training_data(
    files: List[UploadFile],
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin) 
) -> Any:
    """
    Upload training data for AI model.
    """
    raise HTTPException(status_code=405, detail="Not implemented")

@router.get("/retrain-status/{task_id}", response_model=FeedbackResponse, summary="Get retrain status")
async def get_retrain_status(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_admin)
) -> Any:
    """
    Get the status of the retraining process.
    """
    raise HTTPException(status_code=405, detail="Not implemented")