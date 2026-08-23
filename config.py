# config.py
import os
import shutil
import sys
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class UIColors:
    """Configurazione centralizzata dei colori UI - Stile Moderno"""

    # Palette Scacchiera e Sfondo
    BIANCO: Tuple[int, int, int] = (240, 236, 212) 
    NERO: Tuple[int, int, int] = (119, 149, 86)
    SFONDO_APP: Tuple[int, int, int] = (48, 46, 43)
    PANEL: Tuple[int, int, int] = (38, 36, 33)
    PANEL_HEADER: Tuple[int, int, int] = (30, 29, 27)
    COORD_TEXT: Tuple[int, int, int] = (255, 255, 255)

    # Testi
    TESTO: Tuple[int, int, int] = (255, 255, 255)
    TESTO_SEC: Tuple[int, int, int] = (170, 170, 170)
    TESTO_ACCENT: Tuple[int, int, int] = (100, 200, 255) # Nuovo colore per Aperture

    # Classificazione Mosse
    BRILLANTE: Tuple[int, int, int] = (20, 255, 209)
    MIGLIORE: Tuple[int, int, int] = (150, 188, 75)
    OTTIMA: Tuple[int, int, int] = (150, 188, 75)
    BUONA: Tuple[int, int, int] = (100, 149, 237)
    IMPRECISIONE: Tuple[int, int, int] = (240, 193, 92)
    ERRORE: Tuple[int, int, int] = (230, 145, 44)
    GRAVE: Tuple[int, int, int] = (201, 52, 48)

    # Elementi UI
    SFONDO_BOTTONE: Tuple[int, int, int] = (60, 60, 60)
    SFONDO_BOTTONE_HOVER: Tuple[int, int, int] = (80, 80, 80)

    # Highlights - CORREZIONE VISIBILITÀ
    HIGHLIGHT_SELECTED: Tuple[int, int, int, int] = (255, 255, 50, 120)
    HIGHLIGHT_LAST_MOVE: Tuple[int, int, int, int] = (255, 255, 50, 100)
    HIGHLIGHT_CHECK: Tuple[int, int, int, int] = (200, 50, 50, 180)
    
    # FIX 2: AUMENTATA VISIBILITÀ (Alpha da 40 a 140)
    HIGHLIGHT_LEGAL_MOVE: Tuple[int, int, int, int] = (20, 20, 20, 140) 
    HIGHLIGHT_LEGAL_CAPTURE: Tuple[int, int, int, int] = (200, 50, 50, 160) 

    # Frecce
    FRECCIA_MIGLIORE: Tuple[int, int, int, int] = (150, 188, 75, 220)

    # Barra valutazione
    EVAL_BG: Tuple[int, int, int] = (30, 30, 30)
    EVAL_DIVIDER:Tuple[int, int, int] = (150, 188, 75)
    EVAL_FORE: Tuple[int, int, int] = (30, 30, 30)
    EVAL_BAR_GOOD: Tuple[int, int, int] = (150, 188, 75)
    EVAL_BAR_BAD: Tuple[int, int, int] = (201, 52, 48)

    # Bordo e linee
    BORDER: Tuple[int, int, int] = (80, 80, 80)
    DIVIDER: Tuple[int, int, int] = (70, 70, 70)

COLORS = UIColors()

# --- Configurazione Paths ---
try:
    BASE_DIR = sys._MEIPASS
except AttributeError:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ASSET_PATH = os.path.join(BASE_DIR, "assets")
PGN_PATH = os.path.join(BASE_DIR, "partite_pgn")

STOCKFISH_DOWNLOAD_URL = "https://stockfishchess.org/download/"

STOCKFISH_MISSING_MESSAGE = (
    "Stockfish engine not found.\n"
    "  1. Download it from " + STOCKFISH_DOWNLOAD_URL + "\n"
    "  2. Either put the executable on your PATH (so that `stockfish` resolves),\n"
    "     or point the STOCKFISH_PATH environment variable at it, e.g.\n"
    "       Windows (PowerShell):  $env:STOCKFISH_PATH = 'C:\\engines\\stockfish.exe'\n"
    "       Linux / macOS:         export STOCKFISH_PATH=/usr/local/bin/stockfish"
)


def resolve_stockfish_path() -> Optional[str]:
    """Locate the Stockfish binary.

    Resolution order:
      1. The STOCKFISH_PATH environment variable (a file path, or a command name
         that can be resolved on PATH).
      2. A `stockfish` executable found on PATH.

    Returns None when no engine can be located; callers are expected to surface
    STOCKFISH_MISSING_MESSAGE in that case. The engine binary is intentionally
    not bundled with this repository (Stockfish is GPLv3).
    """
    env_path = os.environ.get("STOCKFISH_PATH", "").strip().strip('"')
    if env_path:
        if os.path.isfile(env_path):
            return os.path.abspath(env_path)
        resolved = shutil.which(env_path)
        if resolved:
            return resolved

    return shutil.which("stockfish")


STOCKFISH_PATH = resolve_stockfish_path()

# --- Configurazione GUI ---
BOARD_SIZE = 720
SQUARE_SIZE = BOARD_SIZE // 8
ANALYSIS_PANEL_WIDTH = 400 
EVAL_BAR_WIDTH = 24
SCREEN_HEIGHT = BOARD_SIZE
SCREEN_WIDTH = BOARD_SIZE + EVAL_BAR_WIDTH + ANALYSIS_PANEL_WIDTH
PANEL_X = BOARD_SIZE + EVAL_BAR_WIDTH

# --- Configurazione Engine ---
ELO_LEVELS = [800, 1200, 1500, 1800, 2000, 2300, 2700, 3200]
DEFAULT_ELO_INDEX = 2
MATE_SCORE = 10000
EVAL_CAP = 1000

# Gestione profondità
DEPTH_FAST_ANALYSIS = 12
DEPTH_FULL_ANALYSIS = 22

# Soglie Centipawn (Loss)
SOGLIA_MIGLIORE = 5      
SOGLIA_OTTIMA = 15       
SOGLIA_BUONA = 35        
SOGLIA_IMPRECISIONE = 70 
SOGLIA_ERRORE = 150      

# --- Configurazione Performance ---
ANALYSIS_CACHE_SIZE = 200
LEGAL_MOVES_CACHE_SIZE = 100
DIRTY_RECT_ENABLED = False
LAZY_LOADING_ENABLED = False