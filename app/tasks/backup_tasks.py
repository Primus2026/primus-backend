from app.core.celery_worker import celery_app
from app.services.backup_service import BackupService
import asyncio
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger("BACKUP_TASKS")

@celery_app.task(name="app.tasks.create_backup")
def create_backup_task():
    """
    Celery task wrapper for creating backup.
    """
    logger.info("Starting scheduled/manual backup task...")
    try:
        # Run async service method in sync celery task
        filename = async_to_sync(BackupService.create_backup)()
        logger.info(f"Backup task completed successfully. File: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Backup task failed: {e}")
        raise e

@celery_app.task(name="app.tasks.restore_backup")
def restore_backup_task(filename: str):
    """
    Celery task wrapper for restoring backup.
    """
    logger.info(f"Starting restore task for {filename}...")
    try:
        async_to_sync(BackupService.restore_backup)(filename)
        logger.info("Restore task completed successfully.")
        return "Restore completed"
    except Exception as e:
        logger.error(f"Restore task failed: {e}")
        raise e
