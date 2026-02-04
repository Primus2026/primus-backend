import os
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery("base_app", broker=settings.CELERY_BROKER_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    result_backend=settings.CELERY_RESULT_BACKEND,
)

# Import tasks module so they are registered
import app.tasks.report_tasks
import app.tasks.ai_tasks
import app.tasks.product_definition_tasks
import app.tasks.product_stats_tasks
import app.tasks.backup_tasks
import app.tasks.csv_import # Fix: Register import tasks

celery_app.conf.beat_schedule = {
    # Existing schedules
    "generate-daily-reports": {
        "task": "app.tasks.report_tasks.generate_expiry_report_task",
        "schedule": crontab(
            hour=settings.REPORTS_SCHEDULE_HOUR,
            minute=settings.REPORTS_SCHEDULE_MINUTE
        ),
    },
    "retrain-model-nightly": {
        "task": "app.tasks.retrain_model_task",
        "schedule": crontab(
             hour=settings.AI_RETRAIN_SCHEDULE_HOUR,
             minute=settings.AI_RETRAIN_SCHEDULE_MINUTE
        ),
    },
    # New Backup Schedule
    "daily-backup": {
        "task": "app.tasks.create_backup",
        "schedule": crontab(
            hour=settings.BACKUP_SCHEDULE_HOUR,
            minute=settings.BACKUP_SCHEDULE_MINUTE
        ),
    }
}
