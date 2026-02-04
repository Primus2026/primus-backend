from fastapi import APIRouter, Depends, HTTPException, status
from app.core import security, deps
from app.database.models.user import User
from app.services.backup_service import BackupService
from app.tasks.backup_tasks import create_backup_task, restore_backup_task
from app.schemas.msg import Msg
from typing import List, Any
from celery.result import AsyncResult

router = APIRouter()

@router.post("/", response_model=dict)
async def create_backup(
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    Trigger an on-demand backup (Async Background Task).
    """
    task = create_backup_task.delay()
    return {"message": "Backup task initiated", "task_id": task.id}

@router.get("/", response_model=List[dict])
async def list_backups(
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    List all available backups in storage.
    """
    return await BackupService.list_backups()

@router.get("/status/{task_id}", response_model=dict)
async def get_backup_status(
    task_id: str,
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    Get the status of a background backup task.
    """
    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.status == "SUCCESS" else str(task_result.result) if task_result.status == "FAILURE" else None
    }


@router.post("/{filename}/restore", response_model=dict)
async def restore_backup(
    filename: str,
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    Trigger a restore from a specific backup file (Async Background Task).
    WARNING: This will overwrite current data.
    """
    task = restore_backup_task.delay(filename)
    return {"message": f"Restore task initiated for {filename}", "task_id": task.id}
