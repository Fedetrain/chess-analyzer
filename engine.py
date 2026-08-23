# engine.py
import chess
import threading
from stockfish import Stockfish
from typing import Dict, Any, Tuple, Optional
import time

from config import (
    MATE_SCORE, COLORS, STOCKFISH_MISSING_MESSAGE,
    SOGLIA_MIGLIORE, SOGLIA_OTTIMA, SOGLIA_BUONA,
    SOGLIA_IMPRECISIONE, SOGLIA_ERRORE,DEPTH_FAST_ANALYSIS,DEPTH_FULL_ANALYSIS
)
from chess_utils import AnalysisCache, ChessInstructor

class EngineWrapper:
    """Gestisce Stockfish e fornisce analisi arricchite.

    Il percorso del binario è già risolto da config.resolve_stockfish_path():
    qui lo si valida soltanto e si apre la sessione UCI.

    Thread-safety: il protocollo UCI è stateful (set_fen_position seguito da
    una query) e la GUI interroga il motore da più thread (analisi di
    background + turno IA). Ogni sequenza posizione->query è quindi
    serializzata da self._lock, e nessun chiamante esterno deve toccare
    self.stockfish direttamente.
    """

    def __init__(self, path: Optional[str]):
        self._lock = threading.RLock()
        self.analysis_cache = AnalysisCache(max_size=200, timeout_seconds=60)
        self.stockfish = None

        if not path:
            print(STOCKFISH_MISSING_MESSAGE)
            return

        try:
            # Parametri ottimizzati per analisi rapida ma profonda
            parameters = {
                "Threads": 2,
                "Hash": 64,
                "MultiPV": 1, # Analizziamo solo la linea principale per velocità, 3 per approfondimento
                "UCI_LimitStrength": "true",
            }
            self.stockfish = Stockfish(path=path, parameters=parameters)
            self.set_elo(1500)
            print(f"Stockfish ready: {path}")

        except Exception as e:
            print(f"Stockfish initialisation failed: {e}")
            print(STOCKFISH_MISSING_MESSAGE)
            self.stockfish = None

    @property
    def is_ready(self) -> bool:
        return self.stockfish is not None

    def set_elo(self, elo: int) -> None:
        if not self.stockfish: return
        # Clamp ELO tra i limiti accettati da UCI_Elo
        clamped = max(1320, min(3190, elo))
        with self._lock:
            self.stockfish.set_elo_rating(clamped)

    def get_ai_move(self, fen: str) -> Optional[chess.Move]:
        if not self.stockfish: return None
        with self._lock:
            self.stockfish.set_fen_position(fen)
            best = self.stockfish.get_best_move()
        return chess.Move.from_uci(best) if best else None

    def evaluate_position(self, fen: str, depth: int = DEPTH_FAST_ANALYSIS) -> Dict[str, Any]:
        """Valutazione statica della posizione *fen*, dal punto di vista di chi muove.

        La FEN viene sempre impostata esplicitamente prima della query: senza
        questo passaggio si valuterebbe la posizione rimasta in memoria
        dall'ultima analisi, che con più thread attivi è quasi sempre un'altra.
        """
        if not self.stockfish: return {}
        with self._lock:
            self.stockfish.set_fen_position(fen)
            self.stockfish.set_depth(depth)
            return self.stockfish.get_evaluation()

    def get_analysis(self, fen: str, depth: int = DEPTH_FULL_ANALYSIS) -> Dict[str, Any]:
        """Ottiene analisi (valutazione + top moves) con caching."""
        if not self.stockfish: return {}

        # La chiave della cache include la profondità
        cache_key = f"{fen}_{depth}"
        cached = self.analysis_cache.get(cache_key)
        if cached: return cached

        with self._lock:
            self.stockfish.set_fen_position(fen)
            self.stockfish.set_depth(depth)

            eval_data = self.stockfish.get_evaluation()
            top_moves = self.stockfish.get_top_moves(3) # Le prime 3 per i suggerimenti

        result = {
            "fen": fen,          # permette ai chiamanti di verificare a quale posizione si riferisce
            "depth": depth,
            "evaluation": eval_data,
            "top_moves": top_moves,
            "timestamp": time.time()
        }
        self.analysis_cache.set(cache_key, result)
        return result

    def get_fast_analysis(self, fen: str) -> Dict[str, Any]:
        """Wrapper per analisi veloce."""
        return self.get_analysis(fen, depth=DEPTH_FAST_ANALYSIS)


    def classify_move(self, 
                      board_before: chess.Board,
                      move: chess.Move,
                      analysis_before: Dict[str, Any], 
                      eval_after: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifica la mossa e genera una spiegazione (Chatbot).
        Restituisce un dizionario ricco di metadati per la UI.
        """
        
        # Default response structure
        result = {
            "label": "Analisi...",
            "color": COLORS.TESTO_SEC,
            "loss": 0.0,
            "explanation": "Sto analizzando la posizione...",
            "is_best": False
        }

        if not analysis_before.get('top_moves'):
            return result
            
        # 1. Calcolo Punteggi (CP)
        # Normalizziamo tutto dal punto di vista di chi ha fatto la mossa
        player_turn = board_before.turn # Chi ha mosso?
        
        best_move_data = analysis_before['top_moves'][0]
        
        # Punteggio atteso (Miglior mossa possibile)
        score_best = self._normalize_score(best_move_data, player_turn)
        
        # Punteggio effettivo (Dopo la mossa)
        # eval_after è calcolato sulla board DOPO la mossa, quindi tocca all'avversario.
        # Stockfish ritorna CP per chi deve muovere. Quindi invertiamo.
        score_actual = -self._normalize_eval(eval_after)
        
        # Calcolo perdita (Loss) in centipawn
        loss = score_best - score_actual
        loss = max(0, loss) # Non può essere negativa (al massimo 0 se hai trovato una mossa migliore dell'engine a bassa profondità)
        
        result["loss"] = loss / 100.0
        
        # 2. Classificazione
        # Controllo speciale: è la mossa migliore suggerita?
        best_uci = best_move_data.get("Move")
        is_engine_best = (best_uci == move.uci())
        
        if is_engine_best or loss <= SOGLIA_MIGLIORE:
            result["label"] = "★ Migliore"
            result["color"] = COLORS.MIGLIORE
            result["is_best"] = True
            # Se era un sacrificio o mossa complessa, potrebbe essere "Brillante" (logica futura)
        elif loss <= SOGLIA_OTTIMA:
            result["label"] = "Ottima"
            result["color"] = COLORS.OTTIMA
        elif loss <= SOGLIA_BUONA:
            result["label"] = "Buona"
            result["color"] = COLORS.BUONA
        elif loss <= SOGLIA_IMPRECISIONE:
            result["label"] = "Imprecisione"
            result["color"] = COLORS.IMPRECISIONE
        elif loss <= SOGLIA_ERRORE:
            result["label"] = "Errore"
            result["color"] = COLORS.ERRORE
        else:
            result["label"] = "Grave Errore"
            result["color"] = COLORS.GRAVE

        # 3. Generazione Spiegazione (Chatbot)
        board_after = board_before.copy()
        board_after.push(move)
        
        result["explanation"] = ChessInstructor.explain_move(
            board_before, move, result["label"], result["loss"], board_after.is_checkmate()
        )
        
        return result

    def _normalize_score(self, move_data: Dict, turn: bool) -> int:
        """Estrae CP o Mate score normalizzato in CP."""
        val = 0
        if 'Centipawn' in move_data and move_data['Centipawn'] is not None:
            val = move_data['Centipawn']
        elif 'Mate' in move_data and move_data['Mate'] is not None:
            m = move_data['Mate']
            val = (MATE_SCORE - abs(m)*100) if m > 0 else (-MATE_SCORE + abs(m)*100)
        return val

    def _normalize_eval(self, eval_data: Dict) -> int:
        """Simile a sopra ma per il formato output di get_evaluation()."""
        val = eval_data.get('value', 0)
        if eval_data.get('type') == 'mate':
            val = (MATE_SCORE - abs(val)*100) if val > 0 else (-MATE_SCORE + abs(val)*100)
        return val

    def get_move_accuracy(self, fen: str, move: chess.Move) -> float:
        # Placeholder per calcolo accuratezza % (stile chess.com)
        # Richiederebbe un calcolo basato sulla win probability
        return 0.0