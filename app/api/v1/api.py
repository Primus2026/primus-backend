from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, users, rack_CRUD, product_definition_CRUD, 
    reports, stock_outbound, ai, stock, stock_inbound, 
    alerts, backups, voice, camera, gcode
)

api_router = APIRouter()

# Existing Endpoints
api_router.include_router(stock.router, prefix="/stock", tags=["Stock"])
api_router.include_router(stock_outbound.router, prefix="/stock-outbound", tags=["Stock Outbound"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(rack_CRUD.router, prefix="/racks", tags=["Racks"])
api_router.include_router(product_definition_CRUD.router, prefix="/product_definitions", tags=["Product Definitions"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(stock_inbound.router, prefix="/stock-inbound", tags=["Stock Inbound"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Recognition"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(voice.router, prefix="/voice-command", tags=["Voice Command"])
api_router.include_router(backups.router, prefix="/backups", tags=["backups"])

# 3D Printer Warehouse Endpoints (Final Stage)
api_router.include_router(camera.router, prefix="/camera", tags=["Camera"])
api_router.include_router(gcode.router, prefix="/gcode", tags=["G-code Printer"])

