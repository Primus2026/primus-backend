import threading
import time
import logging
from typing import Optional
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
        self.step_mm = 3.0           # Smaller step = smoother motion
        
        # Pick/Place toggle state
        self.is_holding = False      # True = magnet is ON (holding a piece)
        
        # Debounce for hold button
        self.last_action_time = 0
        self.action_debounce = 1.5
        
        # Lock only during actual pick/place execution - NOT during jogging 
        self.is_executing_action = False
        
        self.status_msg = "Gotowy (Tryb WiFi)"

    def report_state(self, x: int, y: int, hold: int):
        """Called by API when ESP32 sends a WiFi report."""
        
        # 1. Action validation (HOLD button press) - toggle pick/place
        if hold == 1:
            self._trigger_toggle_action()
            return

        # Block jog commands while pick/place is executing
        if self.is_executing_action:
            return

        # 2. X and Y Analysis
        CENTER = 2048
        THRESHOLD = 800
        
        dx = 0.0
        dy = 0.0
        
        if x < (CENTER - THRESHOLD):
            dx = -self.step_mm
        elif x > (CENTER + THRESHOLD):
            dx = self.step_mm
            
        # Orientation: Y < center = away from operator = +dy in machine coords
        if y < (CENTER - THRESHOLD):
            dy = self.step_mm
        elif y > (CENTER + THRESHOLD):
            dy = -self.step_mm
            
        if dx != 0 or dy != 0:
            self._send_jog(dx, dy)

    def _send_jog(self, dx: float, dy: float):
        """Fire-and-forget jog - no blocking, no lock. Printer lookahead buffer handles queuing."""
        logger.info(f"Jog: dx={dx}, dy={dy}")
        threading.Thread(target=self._run_jog_safe, args=(dx, dy), daemon=True).start()

    def _run_jog_safe(self, dx: float, dy: float):
        try:
            gcode.jog(dx, dy, 0)
        except ValueError as ve:
            logger.warning(f"BLOKADA JOG: {ve}")
        except Exception as e:
            logger.error(f"GCode Jog ERROR: {e}")

    def _trigger_toggle_action(self):
        """Toggle between pick and place on button press."""
        now = time.time()
        if now - self.last_action_time < self.action_debounce:
            logger.debug("Debounce - ignoruję kliknięcie.")
            return
        self.last_action_time = now
        
        # Toggle state
        self.is_holding = not self.is_holding
        action = "pick" if self.is_holding else "place"
        logger.info(f"Przycisk HOLD → {action.upper()} (is_holding={self.is_holding})")
        
        threading.Thread(target=self._run_action_safe, args=(action,), daemon=True).start()

    def _run_action_safe(self, action_type: str):
        try:
            self.is_executing_action = True
            gcode.joystick_action(action_type)
            logger.info(f"Zakończono: {action_type}")
        except ConnectionError:
            # Drukarka niepodłączona - NIE cofamy toggle stanu, operacja zostanie
            # powtórzona gdy drukarka się połączy (stan logiczny pozostaje spójny)
            logger.warning(f"Drukarka niepodłączona - akcja '{action_type}' pominięta. Stan is_holding={self.is_holding} zachowany.")
        except Exception as e:
            logger.error(f"Błąd akcji {action_type}: {e}")
            # Cofnij toggle TYLKO przy realnym błędzie wykonania (nie przy braku połączenia)
            if action_type == "pick":
                self.is_holding = False
            else:
                self.is_holding = True
            logger.warning(f"Stan is_holding cofnięty do {self.is_holding} z powodu błędu.")
        finally:
            self.is_executing_action = False

    def get_status(self) -> dict:
        return {
            "mode": "WiFi (HTTP POST /report)",
            "is_holding": self.is_holding,
            "is_executing": self.is_executing_action,
            "message": self.status_msg,
            "printer_connected": gcode.is_connected
        }

joystick = JoystickService()
