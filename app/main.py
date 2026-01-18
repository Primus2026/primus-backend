from fastapi import FastAPI
from .core.config import settings
from .api.v1.api import api_router
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: [%(asctime)s][%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from app.core.redis_client import RedisClient
from app.database.session import SessionLocal
from app.services.weight_service import WeightService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_client = RedisClient.get_client()
    async with SessionLocal() as db:
        await WeightService.calculate_and_cache_weights(db)
    yield
    # Shutdown
    await RedisClient.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    lifespan=lifespan
)


origins = ["*"] # will be updated later

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           
    allow_credentials=True,       
    allow_methods=["*"],            
    allow_headers=["*"],            
)

from fastapi.staticfiles import StaticFiles
import os

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount media directory
try:
    media_path = settings.MEDIA_ROOT
    os.makedirs(media_path, exist_ok=True)
except PermissionError:
    # Fallback for local development if /data is not accessible
    media_path = "media"
    os.makedirs(media_path, exist_ok=True)

app.mount("/media", StaticFiles(directory=media_path), name="media")

@app.get("/")
def read_root():
    return {"message": "Hello World"}

