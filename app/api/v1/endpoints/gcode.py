from fastapi import APIRouter, HTTPException
from app.services.gcode_service import gcode
from app.schemas.gcode import (
    ConnectRequest, CommandRequest, MoveRequest,
    GridPositionRequest, JoystickRequest, JoystickActionRequest, PrinterStatusResponse
)

router = APIRouter()

@router.post("/connect", summary="[Finał] Nawiązanie połączenia z drukarką")
async def connect(req: ConnectRequest):
    try:
        return {"status": "ok", "message": gcode.connect(req.port, req.baudrate)}
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))

@router.post("/disconnect", summary="[Finał] Bezpieczne odłączenie")
async def disconnect():
    return {"status": "ok", "message": gcode.disconnect()}

@router.get("/status", response_model=PrinterStatusResponse, summary="[Finał] Odczytanie obecnego stanu/pozycji")
async def get_status():
    return gcode.get_status()

@router.post("/home", summary="[Finał] Auto-Homing G28 (Wybazowanie głowicy)")
async def home():
    try:
        return {"status": "ok", "response": gcode.home()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send", summary="[Finał] Wysłanie jednej ręcznej komendy (np. z manualnego joysticka)")
async def send_command(req: CommandRequest):
    try:
        return {"status": "ok", "response": gcode.send_command(req.command, wait_for_ok=req.wait_for_ok)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/move", summary="[Finał] Szybki, surowy dojazd do XYZ milimetrów")
async def move(req: MoveRequest):
    try:
        return {"status": "ok", "response": gcode.move_to(req.x, req.y, req.z, req.speed)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/move-to-grid", summary="[Finał] Dojazd magnesem nad konkretne pole(1-8, 1-8)")
async def move_to_grid(req: GridPositionRequest):
    try:
        return {"status": "ok", "response": gcode.move_to_grid(req.col, req.row)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/move-camera-to-grid", summary="[Finał] Dojazd kamerą nad konkretne pole(1-8, 1-8) z uwzględnieniem offsetu")
async def move_camera_to_grid(req: GridPositionRequest):
    try:
        return {"status": "ok", "response": gcode.move_camera_to_grid(req.col, req.row)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/pick", summary="[Finał] Pick (pobranie elementu z magazynu)")
async def pick(req: GridPositionRequest):
    try:
        return {"status": "ok", "response": gcode.pick_from_grid(req.col, req.row, req.level)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/place", summary="[Finał] Place (odłożenie do magazynu)")
async def place(req: GridPositionRequest):
    try:
        return {"status": "ok", "response": gcode.place_on_grid(req.col, req.row, req.level)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jog", summary="[Finał] Joystick programowy, przesunięcie o np. dx=10mm w prawo, użycie G91")
async def jog(req: JoystickRequest):
    try:
        return {"status": "ok", "response": gcode.jog(req.dx, req.dy, req.dz, req.speed)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/magnet/on", summary="[Finał] Włącz elektromagnes")
async def magnet_on():
    try:
        return {"status": "ok", "response": gcode.magnet_on()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/magnet/off", summary="[Finał] Wyłącz elektromagnes")
async def magnet_off():
    try:
        return {"status": "ok", "response": gcode.magnet_off()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/joystick/action", summary="[Finał] Pick/Place z aktualnej pozycji joysticka (z ochroną krawędzi)")
async def joystick_action(req: JoystickActionRequest):
    """
    Wywietla pick lub place z aktualnej pozycji drukarki (gdzie stoi głowica po sterowaniu joystickiem).
    
    Backend sprawdza:
    1. Czy głowica jest w obszarze siatki 8x8 (nie poza szachownicą)
    2. Czy głowica jest wystarczająco blisko środka pola (±8mm tolerancja)
    
    Akcje:
    - **pick** - Pobiera element (magnes ON, podnosi)
    - **place** - Nakłada element (opuszcza, magnes OFF)
    """
    try:
        result = gcode.joystick_action(req.action)
        return result
    except ValueError as e:
        # Blokada bezpieczeństwa - głowica poza siatką lub zbyt daleko od środka pola
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
