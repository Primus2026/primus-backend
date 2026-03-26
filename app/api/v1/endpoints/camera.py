"""
Endpoint kamery USB — snapshot, skanowanie QR, piktogramy.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from app.services.camera_service import camera

router = APIRouter()

@router.get("/snapshot")
async def get_snapshot():
    """Zwraca odczyt z kamery jako obraz JPEG (do wyświetlania podglądu w interfejsie)."""
    try:
        jpeg_bytes = camera.get_jpeg_snapshot()
        return Response(content=jpeg_bytes, media_type="image/jpeg", headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        })
    except RuntimeError as e:
        return {"status": "error", "detail": str(e)}

@router.post("/scan-qr")
async def scan_qr():
    """Wymusza zrobienie zdjęcia i zdekodowanie kodu QR z planszy."""
    try:
        result = camera.decode_qr()
        if result:
            return {"status": "ok", "qr_code": result}
        return {"status": "not_found", "qr_code": None}
    except RuntimeError as e:
        return {"status": "error", "detail": str(e)}

@router.post("/scan-pictogram")
async def scan_pictogram():
    """Wymusza zrobienie zdjęcia i rozpoznanie piktogramu (YOLO)."""
    try:
        result = camera.recognize_pictogram()
        if result:
            return {"status": "ok", "recognized": result}
        return {"status": "not_found", "recognized": None}
    except RuntimeError as e:
        return {"status": "error", "detail": str(e)}
