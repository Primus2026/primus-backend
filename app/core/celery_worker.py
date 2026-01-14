import os
from celery import Celery
from app.core.config import settings



celery_app = Celery("app", include=["app.tasks.csv_import", "app.tasks.product_definition_tasks"])
celery_app.conf.broker_url = settings.CELERY_BROKER_URL
celery_app.conf.result_backend = settings.CELERY_RESULT_BACKEND
celery_app.autodiscover_tasks()

