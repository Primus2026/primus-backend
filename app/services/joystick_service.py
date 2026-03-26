import threading
import time
import logging
from typing import Optional
from app.core.config import settings
from app.services.gcode_service import gcode

logger = logging.getLogger("JoystickService")

class JoystickService:
    """Service to handle incoming coordinates and actions from ESP32S3 Matrix via WiFi (HTTP Push)."""
    
    _instance: Optional["JoystickService"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.last_move_time = 0
        self.move_interval = 0.08  # Fast response (12.5 Hz)
        self.step_mm = 5.0
        
        # Debounce
        self.last_action_time = 0
        self.action_debounce = 1.5 
        
        self.is_jogging = False
        
        self.status_msg = "Gotowy (Tryb WiFi + Simulation Mode)"

    def report_state(self, x: int, y: int, hold: int):
        """Called by API when ESP32 sends a WiFi report."""
        
        # 1. Action Validation (HOLD button)
        if hold == 1:
            self._trigger_gcode_action("pick")
            return

        # 2. X and Y Analysis
        CENTER = 2048
        THRESHOLD = 800
        
        dx = 0
        dy = 0
        
        if x < (CENTER - THRESHOLD):
            dx = -self.step_mm
        elif x > (CENTER + THRESHOLD):
            dx = self.step_mm
            
        # Orientation fix: Y < center is "Up" (away from operator) -> +dy
        if y < (CENTER - THRESHOLD):
            dy = self.step_mm
        elif y > (CENTER + THRESHOLD):
            dy = -self.step_mm
            
        if (dx != 0 or dy != 0):
            self._send_jog(dx, dy)

    def _send_jog(self, dx: float, dy: float):
        """Sends movement command via safe jog logic."""
        if self.is_jogging:
            # Drop the frame if the system is still confirming the previous move
            return
            
        logger.info(f"WiFi-Joystick Ruch: dx={dx}, dy={dy}")
        
        if not gcode.is_connected:
            # DRY RUN LOGGING
            logger.info(f"[DRY-RUN] Jogging (z weryfikacją granic): X{dx} Y{dy}")
            return
            
        # Spin up a thread to run the blocking gcode.jog
        threading.Thread(target=self._run_jog_safe, args=(dx, dy), daemon=True).start()

    def _run_jog_safe(self, dx: float, dy: float):
        try:
            self.is_jogging = True
            gcode.jog(dx, dy, 0)
        except ValueError as ve:
             # Limitatory bezpieczeństwa z gcode_service złapały błąd
             logger.warning(f"BLOKADA JOG: {ve}")
        except Exception as e:
            logger.error(f"GCode Jog ERROR: {e}")
        finally:
            self.is_jogging = False

    def _trigger_gcode_action(self, action_type: str):
        now = time.time()
        if now - self.last_action_time < self.action_debounce:
            return
            
        self.last_action_time = now
        logger.info(f"Otrzymano WiFi-Trigger: {action_type}.")
        
        if not gcode.is_connected:
            logger.info(f"[DRY-RUN] Akcja: {action_type} (centrowanie + ruch osiowy)")
            return
            
        threading.Thread(target=self._run_action_safe, args=(action_type,), daemon=True).start()
        
    def _run_action_safe(self, action_type: str):
        try:
            gcode.joystick_action(action_type)
        except Exception as e:
            logger.error(f"Błąd akcji: {e}")

    def get_status(self) -> dict:
        return {
            "mode": "WiFi (HTTP POST /report)",
            "last_move": self.last_move_time,
            "message": self.status_msg,
            "printer_connected": gcode.is_connected
        }

joystick = JoystickService()
