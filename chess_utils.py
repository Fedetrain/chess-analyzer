
import chess
from typing import Set, List, Optional, Dict, Any, Tuple
from functools import lru_cache
import time
from config import LEGAL_MOVES_CACHE_SIZE

# --- DATABASE APERTURE BASATO SU FEN (Per match esatti/trasposizioni) ---
OPENINGS_FEN_DB = {
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3": "Apertura di Re (e4)",
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3": "Apertura di Donna (d4)",
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6": "Difesa Scandinava",
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6": "Difesa Siciliana",
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": "Difesa Francese",
    "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": "Difesa Caro-Kann",
    "rnbqkbnr/pppppp1p/6p1/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -": "Difesa Moderna",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/3P4/PPP2PPP/RNBQKBNR b KQkq -": "Apertura Ponziani / Philidor",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -": "Attacco di Re (Cavallo f3)",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": "Partita Spagnola / Italiana (Base)",
    "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq -": "Ruy Lopez (Spagnola)",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq -": "Partita Italiana",
    "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq -": "Difesa Indiana",
    "rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR b KQkq -": "Difesa Indiana (Generica)",
    "rnbqkb1r/pp1ppppp/2p2n2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -": "Difesa Slava",
    "rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -": "Difesa Philidor"
}

# --- NUOVO: DATABASE APERTURE BASATO SU SEQUENZE DI MOSSE (UCI) ---
# Copre le varianti comuni nelle prime 5 mosse
OPENINGS_SEQUENCES = {
    "e2e4 c7c5": "Difesa Siciliana",
    "e2e4 e7e5 g1f3 b8c6 f1b5": "Ruy Lopez (Spagnola)",
    "e2e4 e7e5 g1f3 b8c6 f1c4": "Partita Italiana",
    "e2e4 e7e5 g1f3 b8c6 c2c3": "Apertura Ponziani",
    "d2d4 d7d5 c2c4": "Gambetto di Donna",
    "d2d4 g8f6 c2c4 e7e6": "Difesa Nimzo-Indiana / Bogo-Indiana",
    "d2d4 d7d5 c2c4 c7c6": "Difesa Slava",
    "e2e4 e7e6": "Difesa Francese",
    "e2e4 c7c6": "Difesa Caro-Kann",
    "e2e4 d7d6": "Difesa Pirc / Moderna",
    "g1f3 d7d5": "Apertura Réti",
    "e2e4 g6": "Difesa Moderna/Pirc (G6)",
    "e2e4 d5": "Difesa Scandinava",
    "d2d4 g8f6 c2c4 g7g6": "Difesa Est-Indiana",
    "d2d4 d7d5 g1f3 g8f6 c2c4 e6": "Gambetto di Donna Accettato/Rifiutato"
    # Aggiungi qui tutte le sequenze che trovi utili
}


class ChessUtils:
    """Funzioni di utilità di basso livello per gli scacchi."""
    
    @staticmethod
    @lru_cache(maxsize=LEGAL_MOVES_CACHE_SIZE)
    def get_legal_moves_cached(fen: str) -> Set[chess.Move]:
        board = chess.Board(fen)
        return set(board.legal_moves)
    
    @staticmethod
    def identify_opening(board: chess.Board) -> str:
        """
        Tenta di identificare l'apertura corrente usando prima le sequenze di mosse
        e poi il FEN rigido per maggiore precisione.
        """
        move_count = len(board.move_stack)
        
        if move_count < 2: return "Inizio Partita"
        if move_count > 20: return "Medio Gioco" # Limite per la ricerca di apertura

        # 1. Metodo Sequenza di Mosse (più flessibile)
        # Converte lo stack di mosse in una stringa UCI
        uci_sequence = " ".join([move.uci() for move in board.move_stack])
        best_match = None
        
        # Cerca la sequenza più lunga che corrisponde
        for sequence, name in sorted(OPENINGS_SEQUENCES.items(), key=lambda item: len(item[0]), reverse=True):
            if uci_sequence.startswith(sequence):
                best_match = name
                break
        
        if best_match:
            return best_match

        # 2. Metodo FEN Rigido (per posizioni precise)
        fen_parts = board.fen().split(' ')
        fen_key = " ".join(fen_parts[:4])
        
        if fen_key in OPENINGS_FEN_DB:
            return OPENINGS_FEN_DB[fen_key]
        
        # 3. Fallback
        return "Apertura non comune"

    @staticmethod
    def get_material_diff(board: chess.Board) -> int:
        values = {
            chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
            chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
        }
        score = 0
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                val = values.get(piece.piece_type, 0)
                score += val if piece.color == chess.WHITE else -val
        return score

class ChessInstructor:

    @staticmethod
    def explain_move(board_before: chess.Board, move: chess.Move, 
                     classification: str, loss: float, is_checkmate: bool) -> str:
        
        # 1. Contesto di base
        board_after = board_before.copy()
        board_after.push(move)
        
        is_capture = board_before.is_capture(move)
        piece_moved = board_before.piece_at(move.from_square)
        piece_name = ChessInstructor._get_piece_name(piece_moved)
        is_check = board_after.is_check()
        
        # --- NUOVE EURISTICHE AVANZATE ---
        
        # A. Controllo del Centro (e4, d4, e5, d5)
        center_squares = [chess.E4, chess.D4, chess.E5, chess.D5]
        controls_center = move.to_square in center_squares
        
        # B. Sviluppo Pezzi Leggeri (Cavalli/Alfieri)
        is_development = False
        if piece_moved and piece_moved.piece_type in [chess.KNIGHT, chess.BISHOP]:
            rank_from = chess.square_rank(move.from_square)
            if (piece_moved.color == chess.WHITE and rank_from == 0) or \
               (piece_moved.color == chess.BLACK and rank_from == 7):
                is_development = True

        # C. Sicurezza del Re (Arrocco)
        is_castling = board_after.is_castling(move)
        
        # --- GENERAZIONE TESTO SPIEGAZIONE ---
        
        explanation = ""
        loss_pct = f" (Diff: {loss:.2f})." 

        if is_checkmate:
            return f"★ Scacco Matto! Il {piece_name} chiude la partita definitivamente."

        # Logica combinata: Classificazione + Euristica
        if "Migliore" in classification or "Ottima" in classification:
            if is_castling:
                explanation = "Ottima decisione strategica! Il Re è ora al sicuro."
            elif controls_center:
                explanation = f"Mossa forte! Il {piece_name} occupa il centro e domina la scacchiera."
            elif is_development:
                explanation = f"Eccellente sviluppo. Il {piece_name} entra in gioco attivamente."
            elif is_capture:
                explanation = f"Ottima cattura tattica con il {piece_name}, guadagni materiale o posizione."
            elif is_check:
                explanation = f"Attacco preciso! Metti il Re avversario sotto pressione immediata."
            else:
                explanation = "Hai trovato la linea migliore calcolata dal motore."
                
        elif "Buona" in classification:
            if is_development:
                explanation = "Sviluppo solido. Continua a portare fuori i pezzi leggeri."
            else:
                explanation = "Mossa corretta che mantiene l'equilibrio della posizione."
                
        elif "Imprecisione" in classification:
            explanation = "Non è un errore grave, ma c'erano caselle migliori per mettere pressione."
            
        elif "Errore" in classification:
            if is_capture:
                explanation = "Attenzione: questa cattura concede un vantaggio tattico all'avversario."
            elif board_before.is_check(): 
                explanation = "Uscita dallo scacco sub-ottimale. C'era un modo più sicuro."
            else:
                explanation = f"Errore posizionale. Il {piece_name} qui è vulnerabile o passivo."
                
        elif "Grave" in classification:
            explanation = "Grave errore tattico (Blunder). Rischi di perdere materiale importante o la partita."
            
        else:
            explanation = f"Mossa di {piece_name} analizzata."

        return f"{explanation} {loss_pct}"

    @staticmethod
    def _get_piece_name(piece: Optional[chess.Piece]) -> str:
        if not piece: return "Pezzo"
        names = {
            chess.PAWN: "Pedone", chess.KNIGHT: "Cavallo", chess.BISHOP: "Alfiere",
            chess.ROOK: "Torre", chess.QUEEN: "Donna", chess.KING: "Re"
        }
        return names.get(piece.piece_type, "Pezzo")

class AnalysisCache:
    """LRU cache per i risultati dell'analisi."""
    def __init__(self, max_size: int = 100, timeout_seconds: int = 30):
        self.max_size = max_size
        self.timeout = timeout_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._order: List[str] = []
    
    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache: return None
        data, timestamp = self._cache[key]
        if time.time() - timestamp > self.timeout:
            self._remove(key)
            return None
        self._order.remove(key)
        self._order.append(key)
        return data
    
    def set(self, key: str, data: Any) -> None:
        if key in self._cache: self._order.remove(key)
        elif len(self._cache) >= self.max_size: self._remove_oldest()
        self._cache[key] = (data, time.time())
        self._order.append(key)
    
    def _remove(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
            self._order.remove(key)
    
    def _remove_oldest(self) -> None:
        if self._order: self._remove(self._order[0])