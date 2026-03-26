from pydantic import BaseModel, Field
from typing import Optional

class ConnectRequest(BaseModel):
    port: Optional[str] = Field(default=None, description="Np. COM5 w Windowsie, /dev/ttyUSB0 w Linux. Jeśli None, użyje z configu.")
    baudrate: Optional[int] = Field(default=None, description="Domyślnie z configu (250000)")

class CommandRequest(BaseModel):
    command: str = Field(..., description="Pojedyncza komenda GCode, np 'G28' lub 'M106 S200'")
    wait_for_ok: bool = True

class MoveRequest(BaseModel):
    x: float = Field(..., ge=0, le=280)
    y: float = Field(..., ge=0, le=280)
    z: Optional[float] = Field(None, ge=0, le=50)
    speed: Optional[int] = None

class GridPositionRequest(BaseModel):
    col: int = Field(..., ge=1, le=8, description="Kolumna 1-8")
    row: int = Field(..., ge=1, le=8, description="Wiersz 1-8")
    level: str = Field(default="bottom", description="'bottom' = na dole, 'top' = stakowany drugi element")

class JoystickRequest(BaseModel):
    dx: float = Field(default=0)
    dy: float = Field(default=0)
    dz: float = Field(default=0)
    speed: Optional[int] = None

class PrinterStatusResponse(BaseModel):
    connected: bool
    port: Optional[str] = None
    baudrate: Optional[int] = None
    limits: Optional[dict] = None
    position_raw: Optional[str] = None

class JoystickActionRequest(BaseModel):
    action: str = Field(..., description="'pick' lub 'place' - pobranie lub odlozenie z aktualnej pozycji joysticka")
