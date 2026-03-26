import sys
from unittest.mock import MagicMock

# Podmiana zależności dla testów
sys.modules['app.services.gcode_service'] = MagicMock()
sys.modules['app.services.camera_service'] = MagicMock()

from app.services.chess_service import ChessService

service = ChessService()

# Symulujemy stan gdzie mamy 3 wierzchołki cyklu
# Niech "BR" będzie na 0 (A), na jego miejsce ma wejść "WP".
# "WP" jest na 16 (B), na jego miejsce ma wejść "BN".
# "BN" jest na 8 (C), na jego miejsce ma wejść "BR".
# Mamy cykliczną wymianę: BR(0) -> 8, BN(8) -> 16, WP(16) -> 0
# Reszta to None

service.target_board = [None] * 64
service.target_board[8] = "BR"
service.target_board[16] = "BN"
service.target_board[0] = "WP"

service.board_state = [None] * 64
service.board_state[0] = "BR"
service.board_state[8] = "BN"
service.board_state[16] = "WP"

print("Test Graph Solver (Cykl):")
try:
    service.setup_smart()
    print("Zakończono poprawnie. Ostateczny stan:")
    for i in [0, 8, 16]:
         print(f"Pos {i}: {service.board_state[i]}")
         
    if service.board_state[8] == "BR" and service.board_state[16] == "BN" and service.board_state[0] == "WP":
        print("SUCCESS! Cykl został prawidłowo rozwiązany.")
    else:
        print("BŁĄD logiki.")
except Exception as e:
    import traceback
    traceback.print_exc()

# Test łańcucha i prostej drogi
print("\nTest Ścieżek prostych Nearest Neighbor:")
service.board_state = [None] * 64
service.board_state[0] = "WP"
service.board_state[1] = "WP"

service.target_board = [None] * 64
service.target_board[63] = "WP"
service.target_board[62] = "WP"

try:
    service.setup_smart()
    if service.board_state[63] == "WP" and service.board_state[62] == "WP":
        print("SUCCESS! Ścieżki proste przetestowane.")
    else:
        print("BŁĄD logiki w Nearest Neighbor")
except Exception as e:
    import traceback
    traceback.print_exc()

