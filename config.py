# config.py
import os
import shutil
import sys
from dataclasses import dataclass


@dataclass
class UIColors:
    """Configurazione centralizzata dei colori UI - Stile Moderno"""

    # Palette Scacchiera e Sfondo
    BIANCO: tuple[int, int, int] = (240, 236, 212)
    NERO: tuple[int, int, int] = (119, 149, 86)
    SFONDO_APP: tuple[int, int, int] = (48, 46, 43)
    PANEL: tuple[int, int, int] = (38, 36, 33)
    PANEL_HEADER: tuple[int, int, int] = (30, 29, 27)
    COORD_TEXT: tuple[int, int, int] = (255, 255, 255)

    # Testi
    TESTO: tuple[int, int, int] = (255, 255, 255)
    TESTO_SEC: tuple[int, int, int] = (170, 170, 170)
    TESTO_ACCENT: tuple[int, int, int] = (100, 200, 255) # Nuovo colore per Aperture

    # Classificazione Mosse
    BRILLANTE: tuple[int, int, int] = (20, 255, 209)
    MIGLIORE: tuple[int, int, int] = (150, 188, 75)
    OTTIMA: tuple[int, int, int] = (150, 188, 75)
    BUONA: tuple[int, int, int] = (100, 149, 237)
    IMPRECISIONE: tuple[int, int, int] = (240, 193, 92)
    ERRORE: tuple[int, int, int] = (230, 145, 44)
    GRAVE: tuple[int, int, int] = (201, 52, 48)

    # Elementi UI
    SFONDO_BOTTONE: tuple[int, int, int] = (60, 60, 60)
    SFONDO_BOTTONE_HOVER: tuple[int, int, int] = (80, 80, 80)

    # Highlights - CORREZIONE VISIBILITÀ
    HIGHLIGHT_SELECTED: tuple[int, int, int, int] = (255, 255, 50, 120)
    HIGHLIGHT_LAST_MOVE: tuple[int, int, int, int] = (255, 255, 50, 100)
    HIGHLIGHT_CHECK: tuple[int, int, int, int] = (200, 50, 50, 180)

    # FIX 2: AUMENTATA VISIBILITÀ (Alpha da 40 a 140)
    HIGHLIGHT_LEGAL_MOVE: tuple[int, int, int, int] = (20, 20, 20, 140)
    HIGHLIGHT_LEGAL_CAPTURE: tuple[int, int, int, int] = (200, 50, 50, 160)

    # Frecce
    FRECCIA_MIGLIORE: tuple[int, int, int, int] = (150, 188, 75, 220)

    # Barra valutazione
    EVAL_BG: tuple[int, int, int] = (30, 30, 30)
    EVAL_DIVIDER:tuple[int, int, int] = (150, 188, 75)
    EVAL_FORE: tuple[int, int, int] = (30, 30, 30)
    EVAL_BAR_GOOD: tuple[int, int, int] = (150, 188, 75)
    EVAL_BAR_BAD: tuple[int, int, int] = (201, 52, 48)

    # Bordo e linee
    BORDER: tuple[int, int, int] = (80, 80, 80)
    DIVIDER: tuple[int, int, int] = (70, 70, 70)

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


def resolve_stockfish_path() -> str | None:
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

# --- Engine configuration ---
ELO_LEVELS = [800, 1200, 1500, 1800, 2000, 2300, 2700, 3200]
DEFAULT_ELO_INDEX = 2
MATE_SCORE = 10000
EVAL_CAP = 1000

ENGINE_THREADS = 2
ENGINE_HASH_MB = 64
MULTIPV = 3

# Search depth
DEPTH_FAST_ANALYSIS = 12
DEPTH_FULL_ANALYSIS = 22

#: Stockfish's UCI_Elo option bottoms out here. Verified against the binary
#: ("800 is below UCI_Elo's minimum value of 1320") and against src/search.h
#: (`constexpr static int LowestElo = 1320`).
UCI_ELO_MIN = 1320
UCI_ELO_MAX = 3190


@dataclass(frozen=True)
class StrengthProfile:
    """How to ask the engine to play at a requested Elo.

    Below 1320 ``UCI_Elo`` simply does not exist, so a slider that claims to
    reach 800 has to express weakness some other way. ``Skill Level`` (0-20)
    combined with a node ceiling is the only built-in mechanism that goes
    weaker than 1320, so that is what the low stops use.
    """

    requested_elo: int
    use_uci_elo: bool
    uci_elo: int = UCI_ELO_MIN
    skill_level: int = 20
    node_limit: int | None = None

    @property
    def description(self) -> str:
        if self.use_uci_elo:
            return f"UCI_Elo {self.uci_elo}"
        nodes = f", {self.node_limit} nodes" if self.node_limit else ""
        return f"Skill Level {self.skill_level}{nodes}"


def strength_for_elo(elo: int) -> StrengthProfile:
    """Map a requested Elo onto a real, achievable engine configuration.

    At or above 1320 the engine's own calibrated limiter is used. Below it, the
    rating is approximated with a Skill Level and a node cap; those stops are
    honest approximations, not calibrated ratings, and the UI labels them as
    "approx." accordingly.
    """
    if elo >= UCI_ELO_MIN:
        return StrengthProfile(
            requested_elo=elo,
            use_uci_elo=True,
            uci_elo=max(UCI_ELO_MIN, min(UCI_ELO_MAX, elo)),
        )

    # Interpolate Skill Level 0..7 and a node ceiling across the sub-1320 band.
    span = max(1, UCI_ELO_MIN - 600)
    ratio = max(0.0, min(1.0, (elo - 600) / span))
    skill = int(round(ratio * 7))
    nodes = int(2000 + ratio * 30000)
    return StrengthProfile(
        requested_elo=elo,
        use_uci_elo=False,
        skill_level=max(0, min(20, skill)),
        node_limit=nodes,
    )


# --- Performance ---
ANALYSIS_CACHE_SIZE = 200
LEGAL_MOVES_CACHE_SIZE = 100

# --- Study system ---
#: Where the repertoire, scheduler state and game history live. Overridable so
#: tests never touch a real profile.
DATA_DIR = os.environ.get(
    "CHESS_ANALYZER_DATA", os.path.join(BASE_DIR, "user_data")
)

#: Optional online enrichment. Off by default: the opening explorer host was
#: returning HTTP 401 as of 2026-08-23 (see SOTA.md), so the study system is
#: built offline-first and the network is never on the critical path.
ENABLE_ONLINE_EXPLORER = os.environ.get("CHESS_ANALYZER_ONLINE", "").lower() in (
    "1", "true", "yes",
)
LICHESS_EXPLORER_URL = "https://explorer.lichess.ovh"
EXPLORER_TIMEOUT_SECONDS = 4.0
