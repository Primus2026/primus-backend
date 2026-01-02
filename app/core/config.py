from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Primus 2026 Warehouse API"
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/primus"
    API_V1_STR: str = "/api/v1"

    class Config:
        case_sensitive = True

settings = Settings()
