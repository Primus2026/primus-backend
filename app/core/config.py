from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)
    # DEFAULT VALUES overrideable by environment variables
    PROJECT_NAME: str = "Primus 2026 Warehouse API"
    DATABASE_URL: str = "postgresql+asyncpg://user:password@postgres:5432/primus"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    ADMIN_LOGIN: str = "SUPER_ADMIN"
    ADMIN_PASSWORD: str = "Asdf#1234"
    
    ENVIRONMENT: str = "local"
    ENABLE_DOCS: bool = True

    REDIS_URL: str = "redis://redis:6379/0"

    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL
    CELERY_TIMEZONE: str = "Europe/Warsaw"

    MEDIA_ROOT: str = "/data/media"
    REPORT_DIR: str = "/data/reports"
    MODELS_DIR: str = "/data/models"
    DATASET_DIR: str = "/data/datasets/product_classification"

    # Storage Settings
    STORAGE_TYPE: str = "minio" 

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_EXTERNAL_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    
    # Bucket names
    BUCKET_IMAGES: str = "product-images"
    BUCKET_REPORTS: str = "reports"
    BUCKET_DATASETS: str = "datasets"
    BUCKET_MODELS: str = "models"
    BUCKET_BACKUPS: str = "backups"


    REPORTS_SCHEDULE_HOUR: int = 7
    REPORTS_SCHEDULE_MINUTE: int = 30

    AI_RETRAIN_SCHEDULE_HOUR: int = 2
    AI_RETRAIN_SCHEDULE_MINUTE: int = 0
    
    BACKUP_SCHEDULE_HOUR: int = 3
    BACKUP_SCHEDULE_MINUTE: int = 0

    EXPECTED_CHANGE_TTL: int = 300  # 5 minutes in seconds, controls how long the expected change flag is stored in redis
   
    BACKUP_ENCRYPTION_KEY: str = "XkkN_G-SZUEXzcULZhD3b8w3noM2q_Vt4xBQxmsBDSU="
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.ENVIRONMENT == "production":
            self.ENABLE_DOCS = False



settings = Settings()
