from app.database.session import get_db
from fastapi import APIRouter, File, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.product_definition import (
    ProductDefinitionIn,
    ProductDefinitionOut,
    ProductImportResult,
)
from app.database.models.product_definition import ProductDefinition
from app.core import deps
from app.services.product_definition_service import ProductDefinitionService
from app.database.models.user import User
from app.core.celery_worker import celery_app
from app.tasks.product_definition_tasks import (
    import_product_definitions as import_task,
    bulk_upload_images as bulk_upload_task,
)
from fastapi import Path, HTTPException
import shutil
import os
import uuid
from typing import List

router = APIRouter()


@router.post(
    "/",
    response_model=ProductDefinitionOut
)
async def create_product_definition(
    product_definition: ProductDefinitionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Create a new product definition.

    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.create_product_definition(
        db=db,
        product_definition=product_definition,
    )


@router.post("/{product_definition_id}/upload_image")
async def upload_image(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
    file: UploadFile = File(...),
):
    """
    Upload an image for a product definition.

    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.upload_image(
        db=db,
        product_definition_id=product_definition_id,
        file=file,
    )


@router.post("/bulk-images", response_model=ProductImportResult)
async def bulk_upload_images(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Bulk upload images for product definitions.
    Matches files to products by filename (stored in photo_path).
    Processing is done in background.
    """
    import uuid
    from app.core.config import settings

    # Create a temp dir for this batch in shared volume
    batch_id = str(uuid.uuid4())
    # Use MEDIA_ROOT so both containers can access it (mounted volume)
    temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads", batch_id)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        for file in files:
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        shutil.rmtree(temp_dir)
        raise HTTPException(
            status_code=500, detail=f"Failed to save temporary files: {str(e)}"
        )

    # Trigger Celery task
    task = bulk_upload_task.delay(temp_dir)

    return ProductImportResult(
        message="Bulk image upload started", status="processing", task_id=task.id
    )


@router.get("/bulk-images/{task_id}", response_model=ProductImportResult)
async def get_bulk_upload_status(
    task_id: str = Path(...),
    user: User = Depends(deps.get_current_user),
):
    """
    Get the status of the bulk upload task.
    """
    try:
        task = celery_app.AsyncResult(task_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.state == "PENDING":
        return ProductImportResult(status="processing", task_id=task_id)
    elif task.state == "FAILURE":
        return ProductImportResult(
            status="failed", error=str(task.result), task_id=task_id
        )
    elif task.state == "SUCCESS":
        result_data = task.result
        # Task returns dict matching ProductImportSummary fields?
        # result_data = { "total_processed": 10, "success_count": 5, "error_count": 5, "errors": [...] }

        summary = None
        if isinstance(result_data, dict):
            summary = result_data

        return ProductImportResult(status="completed", task_id=task_id, summary=summary)

    return ProductImportResult(status="processing", task_id=task_id)


@router.get("/{product_definition_id}", response_model=ProductDefinitionOut)
async def get_product_definition(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        deps.get_current_user
    ),  # Allow read access to authenticated users or public? adhering to strict for now but easily changeable
):
    """
    Get a specific product definition by ID.
    """
    return await ProductDefinitionService.get_product_definition(
        db=db, product_definition_id=product_definition_id
    )


@router.get("/", response_model=list[ProductDefinitionOut])
async def get_product_definitions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Get all product definitions.
    """
    return await ProductDefinitionService.get_product_definitions(
        db=db, skip=skip, limit=limit
    )


@router.delete("/{product_definition_id}")
async def delete_product_definition(
    product_definition_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Delete a product definition and its associated image.

    Can only be executed by an admin user.
    """
    return await ProductDefinitionService.delete_product_definition(
        db=db, product_definition_id=product_definition_id
    )


@router.post("/import_csv", response_model=ProductImportResult)
async def import_product_definitions_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(deps.get_current_user),
):
    """
    Import product definitions from a CSV file (Asynchronous).

    Can only be executed by an admin user.
    """
    content = await file.read()
    task = import_task.delay(content)

    return ProductImportResult(
        message="Import started successfully", status="processing", task_id=task.id
    )


@router.get("/import_csv/{task_id}", response_model=ProductImportResult)
async def get_import_result(
    task_id: str = Path(...),
    user: User = Depends(deps.get_current_user),
):
    """
    Get the status/result of the import task.
    """
    try:
        task = celery_app.AsyncResult(task_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.state == "PENDING":
        return ProductImportResult(status="processing", task_id=task_id)
    elif task.state == "FAILURE":
        return ProductImportResult(
            status="failed", error=str(task.result), task_id=task_id
        )
    elif task.state == "SUCCESS":
        result_data = task.result
        # Ensure correct status if not present
        if isinstance(result_data, dict):
            if "status" not in result_data:
                result_data["status"] = "completed"
            result_data["task_id"] = task_id
        return ProductImportResult(**result_data)

    return ProductImportResult(status="processing", task_id=task_id)
