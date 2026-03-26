from fastapi import FastAPI, Request
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

from app.database.init_db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_client = RedisClient.get_client()
    async with SessionLocal() as db:
        await init_db(db)
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

@app.middleware("http")
async def strip_trailing_slash(request: Request, call_next):
    if request.url.path.endswith("/") and request.url.path != "/":
        request.scope["path"] = request.url.path.rstrip("/")
    response = await call_next(request)
    return response


origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
    "https://localhost:8443",
    "https://localhost:443",
    "https://localhost",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5173",
] # Add more origins as needed

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           
    allow_credentials=True,       
    allow_methods=["*"],            
    allow_headers=["*"],            
)

from fastapi.middleware.trustedhost import TrustedHostMiddleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "backend", "nginx"])

from fastapi.staticfiles import StaticFiles
import os

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def read_root():
    return {"message": "Hello World"}

