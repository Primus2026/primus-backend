from fastapi import APIRouter
from app.api.v1.endpoints import auth, users
from app.api.v1.endpoints import rack_CRUD
from app.api.v1.endpoints import product_definition_CRUD
from app.api.v1.endpoints import reports

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(rack_CRUD.router, prefix="/racks", tags=["Racks"])
api_router.include_router(product_definition_CRUD.router, prefix="/product_definitions", tags=["Product Definitions"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
 