import os
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from celery.signals import worker_process_init
import threading
import asyncio
from app.services.ai_service import AIService


celery_app = Celery("app", include=[
    "app.tasks.csv_import",
    "app.tasks.product_definition_tasks",
    "app.tasks.report_tasks",
    "app.tasks.ai_tasks"
])
celery_app.conf.broker_url = settings.CELERY_BROKER_URL
celery_app.conf.result_backend = settings.CELERY_RESULT_BACKEND
celery_app.autodiscover_tasks()

# Handle model reloading in Celery workers
@worker_process_init.connect
def init_worker(**kwargs):
    """
    Start the AI model update listener in a separate thread for each worker process.
    """
    def run_listener():
        try:
            asyncio.run(AIService.listen_for_updates())
        except Exception as e:
            print(f"Error in Celery AI listener: {e}")

    t = threading.Thread(target=run_listener, daemon=True)
    t.start()

celery_app.conf.beat_schedule = {
    # Expiry report handling 
    "scheduled-expiry-check-every-24h": {
        "task": "app.tasks.report_tasks.generate_expiry_report_task",
        "schedule": crontab(hour=settings.REPORTS_SCHEDULE_HOUR, minute=settings.REPORTS_SCHEDULE_MINUTE),
    },
    "cleanup-old-reports-every-24h": {
        "task": "app.tasks.report_tasks.cleanup_old_reports_task",
        "schedule": crontab(hour=settings.REPORTS_SCHEDULE_HOUR, minute=settings.REPORTS_SCHEDULE_MINUTE),
    },
    "scheduled-audit-report": {
        "task": "app.tasks.report_tasks.generate_audit_report_task",
        "schedule": crontab(hour=settings.REPORTS_SCHEDULE_HOUR, minute=settings.REPORTS_SCHEDULE_MINUTE),
    },
    "scheduled-ai-retrain": {
        "task": "app.tasks.ai_tasks.retrain_model_task",
        "schedule": crontab(hour=settings.AI_RETRAIN_SCHEDULE_HOUR, minute=settings.AI_RETRAIN_SCHEDULE_MINUTE),
    }
}

