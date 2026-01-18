import os
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings



celery_app = Celery("app", include=[
    "app.tasks.csv_import",
    "app.tasks.product_definition_tasks",
    "app.tasks.report_tasks"
])
celery_app.conf.broker_url = settings.CELERY_BROKER_URL
celery_app.conf.result_backend = settings.CELERY_RESULT_BACKEND
celery_app.autodiscover_tasks()

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
    }
}

