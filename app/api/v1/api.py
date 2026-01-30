from fastapi import APIRouter
from app.api.v1.endpoints import auth, users
from app.api.v1.endpoints import rack_CRUD
from app.api.v1.endpoints import product_definition_CRUD
from app.api.v1.endpoints import reports
from app.api.v1.endpoints import stock_outbound
from app.api.v1.endpoints import ai
from app.api.v1.endpoints import stock
from app.api.v1.endpoints import stock_inbound
from app.api.v1.endpoints import alerts
from app.api.v1.endpoints import backups

api_router = APIRouter()
api_router.include_router(stock.router, prefix="/stock", tags=["Stock"])
api_router.include_router(stock_outbound.router, prefix="/stock/outbound", tags=["Stock Outbound"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(rack_CRUD.router, prefix="/racks", tags=["Racks"])
api_router.include_router(product_definition_CRUD.router, prefix="/product_definitions", tags=["Product Definitions"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(stock_inbound.router, prefix="/stock/inbound", tags=["Stock Inbound"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Recognition"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(backups.router, prefix="/backups", tags=["backups"])