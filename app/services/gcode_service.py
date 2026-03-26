"""
Serwis sterowania drukarką 3D (magazynem) po porcie serial/COM z G-code.
Parametry z pliku demo:
- M106 S200 = magnes ON, M107 = magnes OFF
- Z0 = dół, Z4.2 = stack, Z14 = transport
- Siatka 8×8: co 30mm, start (31,31)
- G1 ruch liniowy, F3000 XY, F1000 Z
"""

import serial
import threading
import time
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("GCodeService")

class GCodeService:
    """Singleton — centralny punkt dostępu do komunikacji szeregowej z drukarką."""
    
    _instance: Optional["GCodeService"] = None
    _lock = threading.Lock()

    # === PARAMETRY Z DEMO G-CODE ===
    Z_BOTTOM = 0.0          # Wysokość chwytania elementu na dnie
    Z_STACK = 4.2           # Wysokość chwytania/kładzenia drugiego elementu
    Z_SAFE = 14.0           # Wysokość bezpieczna (przejazdy)
    SPEED_XY = 3000         # Prędkość ruchu w płaszczyźnie XY
    SPEED_Z = 1000          # Prędkość ruchu osi Z

    # === LIMITY BEZPIECZEŃSTWA ===
    SAFE_X_MIN = 0.0
    SAFE_X_MAX = 280.0
    SAFE_Y_MIN = 0.0
    SAFE_Y_MAX = 280.0
    SAFE_Z_MIN = 0.0
    SAFE_Z_MAX = 50.0

    # === SIATKA 8×8 (Magazyn) ===
    GRID_ORIGIN_X = 31.0    # Koordynaty środka pola (kolumna 1, wiersz 1)
    GRID_ORIGIN_Y = 31.0
    CELL_SIZE = 30.0        # Odległość między środkami sąsiednich pól

    # === OFFSET KAMERY WZGLĘDEM MAGNESU ===
    # Pozwala wycentrować kadr nad polem gry (Zadanie Kalibracyjne Osoby C)
    CAMERA_OFFSET_X = -18.0  # Dodaj lub odejmij milimetry, np. -20
    CAMERA_OFFSET_Y = 0.0  # Dodaj lub odejmij milimetry, np. +35

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._serial: Optional[serial.Serial] = None
                    cls._instance._connected = False
                    cls._instance._serial_lock = threading.Lock()
        return cls._instance

    # ──────────────────────────────────────────────
    #  POŁĄCZENIE SERIAL
    # ──────────────────────────────────────────────

    def connect(self, port: Optional[str] = None, baudrate: Optional[int] = None, timeout: float = 5.0) -> str:
        """Otwiera port COM do drukarki."""
        if port is None:
            port = settings.SERIAL_PORT
        if baudrate is None:
            baudrate = settings.SERIAL_BAUDRATE

        if self._connected and self._serial and self._serial.is_open:
            return f"Już połączono z {self._serial.port}"
        
        try:
            self._serial = serial.Serial(port, baudrate, timeout=timeout)
            time.sleep(2)  # Czas na restart kontrolera (typowy w drukarkach 3D na Arduino)
            
            # Wczytywanie powitania z drukarki
            greeting = ""
            while self._serial.in_waiting:
                line = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    greeting += line + "\n"
                    logger.debug(f"Printer init: {line}")
                    
            self._connected = True
            logger.info(f"Podłączono: {port} @ {baudrate}")
            return f"Połączono: {port} @ {baudrate}\n{greeting}"
        except serial.SerialException as e:
            logger.error(f"Błąd połączenia: {e}")
            raise ConnectionError(f"Nie można połączyć z {port}: {e}")

    def disconnect(self) -> str:
        """Rozłącza z drukarką."""
        if self._serial and self._serial.is_open:
            try:
                self.magnet_off()  # Bezpieczeństwo - wyłącz magnes przed rozłączeniem
            except Exception:
                pass
            self._serial.close()
        self._connected = False
        logger.info("Rozłączono z drukarką")
        return "Rozłączono"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    # ──────────────────────────────────────────────
    #  WYSYŁANIE KOMEND G-CODE
    # ──────────────────────────────────────────────

    def send_command(self, cmd: str, wait_for_ok: bool = True, timeout: float = 60.0) -> str:
        """
        Wysyła jedną komendę G-code i czeka na potwierdzenie 'ok'.
        """
        if not self.is_connected:
            logger.warning("Drukarka nie jest podłączona. Automatyczne łaczenie...")
            self.connect()

            
        cmd = cmd.strip()
        if not cmd or cmd.startswith(";"):
            return ""  # Pomijamy komentarze i puste polecenia
            
        # Odrzucamy wbudowane komentarze w tej samej linii
        if ";" in cmd:
            cmd = cmd[:cmd.index(";")].strip()

        with self._serial_lock:
            logger.debug(f"TX: {cmd}")
            self._serial.write(f"{cmd}\n".encode("utf-8"))
            
            if not wait_for_ok:
                return "Wysłano pomyślnie"

            response_lines = []
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self._serial.in_waiting:
                    line = self._serial.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    
                    logger.debug(f"RX: {line}")
                    response_lines.append(line)
                    
                    if line.lower().startswith("ok"):
                        break
                    if "error" in line.lower() or "!! " in line:
                        raise RuntimeError(f"Błąd firmware drukarki: {line}")
                else:
                    time.sleep(0.01)  # Odpoczynek CPU
                    
            return "\n".join(response_lines)

    def send_commands(self, commands: list[str]) -> list[str]:
        """Wysyła listę poleceń sekwencyjnie."""
        return [self.send_command(cmd) for cmd in commands]

    # ──────────────────────────────────────────────
    def _wait_for_position(self, target_x: float, target_y: float, target_z: float, tolerance: float = 0.5, timeout: float = 60.0):
        """Pętla odpytująca drukarkę o aktualną pozycję (M114), blokująca kod do momentu osiągnięcia celu X,Y,Z."""
        import re
        start_time = time.time()
        while time.time() - start_time < timeout:
            resp = self.send_command("M114")
            match_x = re.search(r'X:([-+]?\d*\.\d+|\d+)', resp)
            match_y = re.search(r'Y:([-+]?\d*\.\d+|\d+)', resp)
            match_z = re.search(r'Z:([-+]?\d*\.\d+|\d+)', resp)
            
            if match_x and match_y and match_z:
                curr_x = float(match_x.group(1))
                curr_y = float(match_y.group(1))
                curr_z = float(match_z.group(1))
                
                # Sprawdzamy czy głowica jest w sferze tolerancji
                if (abs(curr_x - target_x) <= tolerance and
                    abs(curr_y - target_y) <= tolerance and
                    abs(curr_z - target_z) <= tolerance):
                    return # Osiągnięto cel!
                    
            time.sleep(0.05) # Szybkie odpytywanie 20x na sekundę zamiast pół-sekundowych przerw
            
        logger.warning(f"Timeout oczekiwania na pozycję {target_x}, {target_y}, {target_z} (M114)")

    # ──────────────────────────────────────────────
    #  LIMITATORY BEZPIECZEŃSTWA 
    # ──────────────────────────────────────────────

    def _validate_position(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None):
        """Zapobiega wyjazdowi głowicy poza określony, bezpieczny obszar roboczy."""
        if x is not None and not (self.SAFE_X_MIN <= x <= self.SAFE_X_MAX):
            raise ValueError(f"CRITICAL: Koordynata X={x} poza zakresem bezpieczeństwa [{self.SAFE_X_MIN}, {self.SAFE_X_MAX}]")
        if y is not None and not (self.SAFE_Y_MIN <= y <= self.SAFE_Y_MAX):
            raise ValueError(f"CRITICAL: Koordynata Y={y} poza zakresem bezpieczeństwa [{self.SAFE_Y_MIN}, {self.SAFE_Y_MAX}]")
        if z is not None and not (self.SAFE_Z_MIN <= z <= self.SAFE_Z_MAX):
            raise ValueError(f"CRITICAL: Koordynata Z={z} poza zakresem bezpieczeństwa [{self.SAFE_Z_MIN}, {self.SAFE_Z_MAX}]")

        # OCHRONA MARGINESÓW: Zjazd poniżej Z_SAFE jest dozwolony TYLKO wewnątrz obszaru szachownicy
        grid_min_x, grid_max_x = 31.0 - 5.0, 241.0 + 5.0 # Margines błędu +/- 5mm od środków skrajnych pól
        grid_min_y, grid_max_y = 31.0 - 5.0, 241.0 + 5.0
        
        target_z = z if z is not None else self.Z_SAFE # (Uproszczone: domyślnie zakładamy z bezpieczne)
        if target_z < self.Z_SAFE - 0.5:
            # Jeśli próbujemy zjechać na dół, sprawdźmy czy X i Y są w polu gry
            if x is not None and (x < grid_min_x or x > grid_max_x):
                raise ValueError(f"BLOKADA: Opadanie (Z={target_z}) poza szachownicą (X={x}) jest zabronione. Tu jest plastikowa obudowa ramy!")
            if y is not None and (y < grid_min_y or y > grid_max_y):
                raise ValueError(f"BLOKADA: Opadanie (Z={target_z}) poza szachownicą (Y={y}) jest zabronione. Tu jest plastikowa obudowa ramy!")

    # ──────────────────────────────────────────────
    #  KOMENDY RUCHU (Przetworzone z Demo)
    # ──────────────────────────────────────────────

    def home(self) -> str:
        """Pozycjonowanie zerowe (Homing). Musi być robione na start."""
        result = self.send_command("G28")
        # Automatyczny podjazd na bezpieczne Z po home, dla bezpieczeństwa
        self.send_command(f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}")
        return result

    def move_to(self, x: float, y: float, z: Optional[float] = None, speed: Optional[int] = None) -> str:
        """
        Ruch bezpieczny do punktu X,Y.
        Gwarantuje, że przejazd nastąpi najpierw w bezpiecznej wysokości Z_SAFE.
        """
        if z is None:
            z = self.Z_SAFE
            
        self._validate_position(x, y, z)
        
        # 1. Zawsze upewnij się, że jesteś na Safe Z przed ruchem w XY
        self.send_command(f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}")
        # 2. Ruch do XY
        self.send_command(f"G1 X{x} Y{y} F{speed or self.SPEED_XY}")
        # 3. Zjazd na pożądane Z (jeśli inne niż Safe)
        if z != self.Z_SAFE:
            self.send_command(f"G1 Z{z} F{self.SPEED_Z}")
            
        # 4. Magia wymuszająca CZEKANIE AŻ GŁOWICA FIZYCZNIE DOJDZIE DO CELU
        # Wiele firmware ignoruje blokadę M400 wymyśloną dla extruderów, więc twardo odpytujemy zamek (M114)
        self.send_command("M400", timeout=120.0)
        
        self._wait_for_position(x, y, z)
            
        return "Ruch wykonany"

    def magnet_on(self) -> str:
        """Załącza elektromagnes z mocą zapisaną w demo."""
        return self.send_command("M106 S200")

    def magnet_off(self) -> str:
        """Wyłącza elektromagnes."""
        return self.send_command("M107")

    # ──────────────────────────────────────────────
    #  OPERACJE FIZYCZNE MAGZAYNU (Pick & Place)
    # ──────────────────────────────────────────────

    def pick(self, x: float, y: float, z_grab: float = 0.0) -> str:
        """Sekwencja pobrania elementu z podanego XYZ."""
        self._validate_position(x, y, z_grab)
        cmds = [
            f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}",  # [BEZPIECZEŃSTWO] Najpierw max do góry
            f"G1 X{x} Y{y} F{self.SPEED_XY}",      # Dojazd na XY
            f"G1 Z{z_grab} F{self.SPEED_Z}",       # Opadanie
            "M106 S200",                           # Magnes ON
            f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}",  # Podnoszenie urobku
        ]
        return "\n".join(self.send_commands(cmds))

    def place(self, x: float, y: float, z_place: float = 0.0) -> str:
        """Sekwencja odłożenia elementu w danym XYZ."""
        self._validate_position(x, y, z_place)
        cmds = [
            f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}",  # [BEZPIECZEŃSTWO] Najpierw max do góry
            f"G1 X{x} Y{y} F{self.SPEED_XY}",      # Dojazd na XY z urobkiem
            f"G1 Z{z_place} F{self.SPEED_Z}",      # Opadanie na cel
            "M107",                                # Magnes OFF (upuszczenie)
            f"G1 Z{self.Z_SAFE} F{self.SPEED_Z}",  # Podniesienie samej "karetki"
        ]
        return "\n".join(self.send_commands(cmds))

    # ──────────────────────────────────────────────
    #  ABSTRAKCJA SIATKI 8x8
    # ──────────────────────────────────────────────

    def grid_to_xy(self, col: int, row: int) -> tuple[float, float]:
        """Konwertuje kolumnę i wiersz (1-8) na rzeczywiste milimetry wg G-Code demo."""
        if not (1 <= col <= 8 and 1 <= row <= 8):
            raise ValueError(f"Pozycja siatki invalid: col={col}, row={row}")
        
        x = self.GRID_ORIGIN_X + (col - 1) * self.CELL_SIZE
        y = self.GRID_ORIGIN_Y + (row - 1) * self.CELL_SIZE
        
        self._validate_position(x, y)
        return x, y

    def move_to_grid(self, col: int, row: int) -> str:
        """Podjedź głowicą elektromagnesu nad zadane pole siatki (na wys. Z_SAFE)."""
        x, y = self.grid_to_xy(col, row)
        return self.move_to(x, y, self.Z_SAFE)

    def move_camera_to_grid(self, col: int, row: int) -> str:
        """Podjedź kamerą nad zadane pole siatki uwzględniając offset fizyczny montażu."""
        x, y = self.grid_to_xy(col, row)
        cam_x = x + self.CAMERA_OFFSET_X
        cam_y = y + self.CAMERA_OFFSET_Y
        
        # Ochrona przed wyjazdem poza ramę maszyny
        cam_x = max(self.SAFE_X_MIN, min(self.SAFE_X_MAX, cam_x))
        cam_y = max(self.SAFE_Y_MIN, min(self.SAFE_Y_MAX, cam_y))
        
        return self.move_to(cam_x, cam_y, self.Z_SAFE)

    def pick_from_grid(self, col: int, row: int, level: str = "bottom") -> str:
        x, y = self.grid_to_xy(col, row)
        z = self.Z_BOTTOM if level == "bottom" else self.Z_STACK
        return self.pick(x, y, z)

    def place_on_grid(self, col: int, row: int, level: str = "bottom") -> str:
        x, y = self.grid_to_xy(col, row)
        z = self.Z_BOTTOM if level == "bottom" else self.Z_STACK
        return self.place(x, y, z)

    # ──────────────────────────────────────────────
    #  JOYSTICK
    # ──────────────────────────────────────────────

    def jog(self, dx: float = 0, dy: float = 0, dz: float = 0, speed: Optional[int] = None) -> str:
        """Ruch relatywny (np. o +10mm w prawo, -10mm w dół). Chroni przed zahaczeniem magnesem."""
        
        # OCHRONA MAGZAYNU: Pobieranie absolutnej pozycji głowicy w celu kalkulacji kolizji
        try:
            resp = self.send_command("M114")
            import re
            match_x = re.search(r'X:([-+]?\d*\.\d+|\d+)', resp)
            match_y = re.search(r'Y:([-+]?\d*\.\d+|\d+)', resp)
            match_z = re.search(r'Z:([-+]?\d*\.\d+|\d+)', resp)
            
            if match_x and match_y and match_z:
                curr_x = float(match_x.group(1))
                curr_y = float(match_y.group(1))
                curr_z = float(match_z.group(1))
                
                # 1. Sprawdzamy, czy nowy krok nie wyprowadzi głowicy poza ramę [0, 280]!
                self._validate_position(curr_x + dx, curr_y + dy, curr_z + dz)
                
                # 2. Blokada zahaczenia magnesem o ramkę przy ruchu X/Y na dole
                if (dx != 0 or dy != 0) and curr_z < self.Z_SAFE - 0.5:
                    raise ValueError(f"BLOKADA BŁĘDU (Obecne Z={curr_z}mm < {self.Z_SAFE}mm): Aby ruszyć w boki, użyj joystika do góry (+Z), by nie zahaczyć o ścianki siatki magazynu!")
        except ValueError as ve:
            raise ve # Propagujemy bezpośrednio do API
        except Exception as e:
            logger.warning(f"Ostrzeżenie: M114 parsing failed ({e}). Puszczam ruch na ryzyko operatora.")

        cmds = [
            "G91",  # Tryb relatywny
            f"G1 X{dx} Y{dy} Z{dz} F{speed or self.SPEED_XY}",
            "G90",  # Powrót do trybu absolutnego
        ]
        res = "\n".join(self.send_commands(cmds))
        
        # Oczekiwanie na dojazd po Jogu 
        if "curr_x" in locals():
            self._wait_for_position(curr_x + dx, curr_y + dy, curr_z + dz)
            
        return res

    # ──────────────────────────────────────────────
    #  JOYSTICK ACTION (Pick/Place z aktualnej pozycji)
    # ──────────────────────────────────────────────

    def _get_current_position(self) -> tuple[float, float, float]:
        """Odczytuje aktualne XYZ z M114. Zwraca (x, y, z) lub rzuca wyjątkiem."""
        import re
        resp = self.send_command("M114")
        match_x = re.search(r'X:([-+]?\d*\.\d+|\d+)', resp)
        match_y = re.search(r'Y:([-+]?\d*\.\d+|\d+)', resp)
        match_z = re.search(r'Z:([-+]?\d*\.\d+|\d+)', resp)
        if not (match_x and match_y and match_z):
            raise RuntimeError("Nie można odczytać pozycji z M114")
        return float(match_x.group(1)), float(match_y.group(1)), float(match_z.group(1))

    def _snap_to_nearest_grid(self, x: float, y: float) -> tuple[int, int]:
        """
        Na podstawie aktualnych XY odgaduje najbliższe pole siatki (col, row).
        Rzuca wyjątek jeśli głowica jest poza polem gry lub zbyt blisko krawędzi.
        """
        # Oblicz względne pozycje od punktu początkowego siatki
        rel_x = x - self.GRID_ORIGIN_X
        rel_y = y - self.GRID_ORIGIN_Y
        
        # Zaokrąglenie do najbliższego pola
        col = round(rel_x / self.CELL_SIZE) + 1
        row = round(rel_y / self.CELL_SIZE) + 1
        
        # === WALIDACJA BEZPIECZEŃSTWA ===
        # 1. Musi być w granicach siatki
        if not (1 <= col <= 8 and 1 <= row <= 8):
            raise ValueError(
                f"BL0KADA: Głowica jest POZA siatką (col={col}, row={row}). "
                f"Wróć joystickiem do obszaru szachownicy przed podniesieniem!"
            )
        
        # 2. Sprawdzamy, czy jesteśmy wystarczająco blisko środka pola (tolerancja ±8mm)
        expected_x = self.GRID_ORIGIN_X + (col - 1) * self.CELL_SIZE
        expected_y = self.GRID_ORIGIN_Y + (row - 1) * self.CELL_SIZE
        
        if abs(x - expected_x) > 8.0 or abs(y - expected_y) > 8.0:
            raise ValueError(
                f"BLOKADA: Głowica jest zbyt daleko od środka pola ({col},{row}) "
                f"(odchylenie: dx={abs(x-expected_x):.1f}mm, dy={abs(y-expected_y):.1f}mm). "
                f"Wycentruj dokładnie nad polem przed podniesieniem!"
            )
        
        return col, row

    def joystick_action(self, action: str) -> dict:
        """
        Wykonuje pick lub place z AKTUALNEJ POZYCJI głowicy (sterowanej joystickiem).
        Automatycznie sprawdza czy pozycja jest bezpieczna (na środku pola siatki).
        """
        if not self.is_connected:
            raise ConnectionError("Drukarka nie podłączona")
        
        # 1. Odczytaj aktualną pozycję
        curr_x, curr_y, curr_z = self._get_current_position()
        logger.info(f"[Joystick Action] Aktualna pozycja: X={curr_x}, Y={curr_y}, Z={curr_z}")
        
        # 2. Sprawdź bezpieczeństwo i znajdź najbliższe pole siatki
        col, row = self._snap_to_nearest_grid(curr_x, curr_y)
        logger.info(f"[Joystick Action] Zidentyfikowane pole siatki: ({col}, {row})")
        
        # 3. Wykonaj akcję
        if action == "pick":
            result = self.pick_from_grid(col, row)
            return {
                "status": "ok",
                "action": "pick",
                "col": col, "row": row,
                "message": f"Pobrano element z pola ({col}, {row})",
                "response": result
            }
        elif action == "place":
            result = self.place_on_grid(col, row)
            return {
                "status": "ok",
                "action": "place",
                "col": col, "row": row,
                "message": f"Odlozono element na pole ({col}, {row})",
                "response": result
            }
        else:
            raise ValueError(f"Nieznana akcja: '{action}'. Użyj 'pick' lub 'place'.")

    # ──────────────────────────────────────────────
    #  STATUS
    # ──────────────────────────────────────────────

    def get_status(self) -> dict:
        status = {
            "connected": self.is_connected,
            "port": self._serial.port if self._serial else None,
            "baudrate": self._serial.baudrate if self._serial else None,
            "limits": {
                "safe_x": [self.SAFE_X_MIN, self.SAFE_X_MAX],
                "safe_y": [self.SAFE_Y_MIN, self.SAFE_Y_MAX],
                "safe_z": [self.SAFE_Z_MIN, self.SAFE_Z_MAX]
            }
        }
        if self.is_connected:
            try:
                status["position_raw"] = self.send_command("M114")
            except Exception:
                status["position_raw"] = "błąd odczytu"
                
        return status


# Domyślny, globalny singleton dla aplikacji
gcode = GCodeService()
