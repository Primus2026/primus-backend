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
    Uruchomienie backupu na żądanie (Asynchroniczne zadanie w tle).
    """
    task = create_backup_task.delay()
    return {"message": "Backup task initiated", "task_id": task.id}

@router.get("/", response_model=List[dict])
async def list_backups(
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    Pobranie listy dostępnych backupów w magazynie.
    """
    return await BackupService.list_backups()

@router.get("/status/{task_id}", response_model=dict)
async def get_backup_status(
    task_id: str,
    current_user: User = Depends(deps.get_current_admin),
) -> Any:
    """
    Pobranie statusu zadania backupu/przywracania.
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
    Przywrócenie kopii zapasowej z pliku (Asynchroniczne zadanie w tle).
    UWAGA: Ta operacja nadpisze obecne dane w bazie.
    """
    task = restore_backup_task.delay(filename)
    return {"message": f"Restore task initiated for {filename}", "task_id": task.id}
