from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.joystick_service import joystick

router = APIRouter()

class StartCommand(BaseModel):
    port: Optional[str] = None

class JoystickReport(BaseModel):
    x: int
    y: int
    hold: int

@router.get("/status")
def get_status():
    """Zwraca obecny status serwisu nasłuchującego Joystick/ESP32S3."""
    return joystick.get_status()

@router.post("/report")
def report_joystick_state(data: JoystickReport):
    """Odbiera raport stanu z matrycy ESP32S3 po WiFi."""
    joystick.report_state(data.x, data.y, data.hold)
    return {"status": "received"}

@router.post("/start")
def start_joystick(cmd: StartCommand):
    """Dla kompatybilności wstecznej - w trybie WiFi nieużywane."""
    return {"message": "Tryb WiFi aktywny - używaj /report", "status": joystick.get_status()}
