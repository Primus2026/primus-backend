import os
from celery import Celery
from app.core.config import settings



celery_app = Celery("app", include=[
    "app.tasks.csv_import",
    "app.tasks.product_definition_tasks",
    "app.tasks.report_tasks"
])
celery_app.conf.broker_url = settings.CELERY_BROKER_URL
celery_app.conf.result_backend = settings.CELERY_RESULT_BACKEND
celery_app.autodiscover_tasks()

celery_app.conf.beat_schedule = {\

    # Expiry report handling 
    "scheduled-expiry-check-every-24h": {
        "task": "app.tasks.report_tasks.scheduled_expiry_check_task",
        "schedule": 86400.0,  # 24 hours
    },
    "cleanup-old-reports-every-24h": {
        "task": "app.tasks.report_tasks.cleanup_old_reports_task",
        "schedule": 86400.0,
    },
}

