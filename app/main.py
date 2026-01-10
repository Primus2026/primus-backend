from fastapi import FastAPI
from .core.config import settings
from .api.v1.api import api_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None
)


origins = ["*"] # will be updated later

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           
    allow_credentials=True,       
    allow_methods=["*"],            
    allow_headers=["*"],            
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {"message": "Hello World"}

