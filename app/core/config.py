from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)

    PROJECT_NAME: str = "Primus 2026 Warehouse API"
    DATABASE_URL: str = "postgresql+asyncpg://user:password@postgres:5432/primus"
    API_V1_STR: str = "/api/v1"


settings = Settings()
