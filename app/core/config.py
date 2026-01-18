from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)

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

    REPORTS_SCHEDULE_HOUR: int = 7
    REPORTS_SCHEDULE_MINUTE: int = 30

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
