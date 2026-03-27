"""
Kamera serwisu.
Przerzucono odpowiedzialność za sprzęt (OpenCV, pyzbar) na natywny Worker Windowsowy,
aby uniknąć problemów z podłączaniem sprzętu do WSL2 / Dockera (timeouty na USB/V4L2).
Ten serwis działa jako proste proxy do: http://host.docker.internal:8001
"""

import requests
import logging
from typing import Optional

logger = logging.getLogger("CameraService")

WINDOWS_AI_URL = "http://host.docker.internal:8001"

class CameraService:
    """Proxy dla natywnej kamery Windows (omija WSL)."""

    def __init__(self):
        pass

    def get_jpeg_snapshot(self) -> bytes:
        """Pobiera klatkę (bytes) bezpośrednio z Windowsa."""
        try:
            resp = requests.get(f"{WINDOWS_AI_URL}/snapshot", timeout=10.0)
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd komunikacji z Windows AI (GET /snapshot): {e}")
            raise RuntimeError(f"Błąd komunikacji z kamerą (Windows AI Worker): {e}")

    def decode_qr(self) -> Optional[str]:
        """Prosi Windowsowy skrypt o odczytanie QR z aktualnej klatki kamery."""
        try:
            resp = requests.get(f"{WINDOWS_AI_URL}/scan-qr", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    return data.get("qr_code")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd komunikacji z Windows AI (GET /scan-qr): {e}")
            return None

    def recognize_pictogram(self) -> Optional[str]:
        """Prosi Windowsowy skrypt o rozpoznanie figury (YOLO) z aktualnej klatki kamery."""
        try:
            # Endpoint na Windowsie zmieniamy na GET, ponieważ to Windows trzyma kamerę
            resp = requests.get(f"{WINDOWS_AI_URL}/analyze-pictogram", timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    logger.info(f"YOLO Windows zwróciło: {data.get('name')} (conf: {data.get('confidence')})")
                    return str(data.get("name"))
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd komunikacji z Windows AI na porcie 8001: {e}")
            return None



# Główna instancja singelton 
camera = CameraService()

