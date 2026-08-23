# game.py
import pygame
import chess
import os
import threading
from typing import Optional, Dict, Any, Tuple, List
import time

from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, STOCKFISH_PATH, ASSET_PATH, 
    BOARD_SIZE, SQUARE_SIZE, DEFAULT_ELO_INDEX, ELO_LEVELS,
    PGN_PATH, LAZY_LOADING_ENABLED, COLORS
)
from engine import EngineWrapper
from drawing import Drawing
from ui import UIManager
from pgn_handler import PGNHandler
from chess_utils import ChessUtils

class AssetManager:
    """Gestisce il caricamento degli assets."""
    def __init__(self):
        self.piece_images: Dict[str, Optional[pygame.Surface]] = {}
        self.sounds: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._loaded = False
    
    def load_piece_images(self) -> Dict[str, pygame.Surface]:
        if not self._loaded:
            pieces = ['wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK']
            for piece in pieces:
                path = os.path.join(ASSET_PATH, f"{piece}.png")
                if os.path.exists(path):
                    self.piece_images[piece] = pygame.transform.smoothscale(
                        pygame.image.load(path).convert_alpha(), 
                        (SQUARE_SIZE, SQUARE_SIZE)
                    )
                else:
                    self.piece_images[piece] = None
            self._loaded = True
        return self.piece_images
    
    def preload_essential(self) -> None:
        if LAZY_LOADING_ENABLED:
            for piece in ['wK', 'bK']:
                path = os.path.join(ASSET_PATH, f"{piece}.png")
                if os.path.exists(path):
                    self.piece_images[piece] = pygame.transform.smoothscale(
                        pygame.image.load(path).convert_alpha(), (SQUARE_SIZE, SQUARE_SIZE)
                    )

class Game:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.mixer.init()
        
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Gem Scacchi - AI Trainer")
        
        self.clock = pygame.time.Clock()
        self.asset_manager = AssetManager()
        self.asset_manager.preload_essential()
        self.piece_images = self.asset_manager.load_piece_images()
        
        # Game State
        self.board = chess.Board()
        self.move_history_san: List[str] = []
        self.selected_square: Optional[int] = None
        self.dragging_piece: Optional[Tuple[pygame.Surface, pygame.Rect]] = None
        
        self.player_color = chess.WHITE
        self.board_orientation = chess.WHITE
        self.last_move: Optional[chess.Move] = None
        # Stato ELO interno del Game (DEVE essere aggiornato)
        self.current_elo = ELO_LEVELS[DEFAULT_ELO_INDEX]
        
        # Analysis State (Nuova Struttura)
        self.current_analysis: Dict[str, Any] = {}
        self.last_move_info: Dict[str, Any] = {
            "label": "", "color": COLORS.TESTO_SEC, 
            "explanation": "Inizia la partita per ricevere consigli.", "loss": 0.0
        }
        
        self.game_state = "loading"
        self.status_text = "Caricamento Stockfish..."
        
        # Components
        self.engine: Optional[EngineWrapper] = None
        self.drawing = Drawing(self.screen, self.piece_images)
        self.pgn_handler = PGNHandler()
        self.chess_utils = ChessUtils()
        
        os.makedirs(PGN_PATH, exist_ok=True)
        
        self.ui = UIManager()
        # Sincronizza lo stato iniziale ELO della UI con quello del Game
        self.ui.current_elo = self.current_elo
        
        self.engine_thread = threading.Thread(target=self.init_engine, args=(STOCKFISH_PATH,), daemon=True)
        self.engine_thread.start()

    def init_engine(self, path: Optional[str]) -> None:
        self.engine = EngineWrapper(path)
        self.engine.set_elo(self.current_elo)
        self.piece_images = self.asset_manager.load_piece_images()
        self.drawing.piece_images = self.piece_images
        self.run_background_analysis()

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                # UI Events
                ui_action = self.ui.handle_event(event)
                if ui_action: self.handle_ui_action(ui_action)
                
                # Board Events
                if not ui_action and self.game_state == "human_turn":
                    self.handle_board_event(event)
            
            # Update UI State
            # ATTENZIONE: Rimosso current_elo da qui, la UI gestisce il proprio stato ELO visivo
            self.ui.update_state(
                game_state=self.game_state,
                status_text=self.status_text,
                last_move_info=self.last_move_info,
                current_analysis=self.current_analysis,
                history_len=len(self.board.move_stack),
                player_color=self.player_color,
                move_history_san=self.move_history_san,
                current_fen=self.board.fen()
            )

            self.drawing.redraw_all(
                self.board, self.board_orientation, self.last_move,
                self.selected_square, self.dragging_piece,
                self.current_analysis, self.ui
            )
            
            self.clock.tick(60)

    def handle_ui_action(self, action: str) -> None:
        if action == "new_game": self.reset_game()
        elif action == "flip": 
            self.board_orientation = not self.board_orientation
            self.drawing.static_board_drawn = False 
        elif action == "color": 
            self.player_color = not self.player_color
            self.board_orientation = self.player_color
            self.reset_game()
            self.drawing.static_board_drawn = False 
        elif action == "undo":
            self.undo_move()
        elif action == "save_pgn": 
            fname = self.pgn_handler.save_game(self.board, PGN_PATH, self.player_color)
            if fname:
                self.status_text = f"Salvato: {fname}"
        elif action == "slider_update":
            # Unico punto in cui l'ELO viene applicato al motore: la UI si limita
            # a esporre il valore scelto (self.ui.current_elo), il Game lo
            # propaga. In precedenza set_elo veniva chiamata anche da
            # UIManager.handle_event, con doppia applicazione per ogni drag.
            self.current_elo = self.ui.current_elo

            if self.engine:
                self.engine.set_elo(self.current_elo)

    def handle_board_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[0] < BOARD_SIZE: self.handle_drag_start(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if event.pos[0] < BOARD_SIZE:
                if self.dragging_piece: self.handle_drag_stop(event.pos)
                else: self.handle_click(event.pos)

    def get_square_from_pos(self, pos: Tuple[int, int]) -> Optional[int]:
        x, y = pos
        if x > BOARD_SIZE or y > BOARD_SIZE or x < 0 or y < 0: return None
        file = x // SQUARE_SIZE
        rank = 7 - (y // SQUARE_SIZE)
        return chess.square(file, rank) if self.board_orientation == chess.WHITE else chess.square(7 - file, 7 - rank)

    def handle_click(self, pos: Tuple[int, int]) -> None:
        square = self.get_square_from_pos(pos)
        if square is None: 
            self.selected_square = None
            return
            
        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                self.selected_square = square
        else:
            move = self.create_move(self.selected_square, square)
            self.attempt_move(move)
            self.selected_square = None

    def handle_drag_start(self, pos: Tuple[int, int]) -> None:
        square = self.get_square_from_pos(pos)
        if square is not None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                self.selected_square = square
                piece_key = ('w' if piece.color == chess.WHITE else 'b') + piece.symbol().upper()
                img = self.piece_images[piece_key]
                rect = img.get_rect(center=pos)
                self.dragging_piece = (img, rect)

    def handle_drag_stop(self, pos: Tuple[int, int]) -> None:
        if self.dragging_piece and self.selected_square is not None:
            target = self.get_square_from_pos(pos)
            if target is not None:
                move = self.create_move(self.selected_square, target)
                self.attempt_move(move)
        self.dragging_piece = None
        self.selected_square = None

    def create_move(self, start: int, end: int) -> chess.Move:
        piece = self.board.piece_at(start)
        if piece and piece.piece_type == chess.PAWN:
            if (piece.color == chess.WHITE and chess.square_rank(end) == 7) or \
               (piece.color == chess.BLACK and chess.square_rank(end) == 0):
                return chess.Move(start, end, promotion=chess.QUEEN)
        return chess.Move(start, end)

    def attempt_move(self, move: chess.Move) -> None:
        if move in self.board.legal_moves:

            fen_before_human_move = self.board.fen()

            self.move_history_san.append(self.board.san(move))
            self.board.push(move)
            self.last_move = move

            # Fotografiamo la posizione risultante: il thread di classificazione
            # deve valutare ESATTAMENTE questa FEN, non "la board attuale", che
            # nel frattempo può già contenere la risposta dell'IA.
            fen_after_human_move = self.board.fen()

            self.game_state = "ai_turn"
            self.status_text = "L'istruttore sta valutando..."

            threading.Thread(
                target=self.process_ai_turn,
                args=(self.current_analysis, move, fen_before_human_move, fen_after_human_move),
                daemon=True
            ).start()
        else:
            self.selected_square = None

    def process_ai_turn(self,
                        analysis_before: Dict[str, Any],
                        human_move: chess.Move,
                        human_move_fen_before: str,
                        human_move_fen_after: Optional[str] = None) -> None:
        if not self.engine: return

        # 0. Verifica che l'analisi "prima della mossa" si riferisca davvero alla
        #    posizione pre-mossa. self.current_analysis è scritta dal thread di
        #    analisi in background e può essere obsoleta (o non ancora pronta)
        #    se l'utente muove velocemente: in quel caso la ricalcoliamo.
        if human_move != chess.Move.null():
            if analysis_before.get("fen") != human_move_fen_before:
                analysis_before = self.engine.get_fast_analysis(human_move_fen_before)

            # 1. Valuta la posizione DOPO la mossa umana.
            #    La FEN va impostata esplicitamente sul motore (evaluate_position
            #    lo fa sotto lock): interrogare get_evaluation() "a secco"
            #    restituirebbe la valutazione dell'ultima posizione caricata da
            #    un altro thread, cioè una classificazione su FEN sbagliata.
            fen_after = human_move_fen_after or self.board.fen()
            eval_after = self.engine.evaluate_position(fen_after)

            # 2. Classifica e spiega (usando lo stato PRIMA della mossa)
            board_before = chess.Board(human_move_fen_before)
            classification_data = self.engine.classify_move(
                board_before, human_move, analysis_before, eval_after
            )
            self.last_move_info = classification_data

        if self.board.is_game_over():
            self.set_game_over_status()
            return

        # 3. Mossa IA
        ai_move = self.engine.get_ai_move(self.board.fen())
        if ai_move:
            self.move_history_san.append(self.board.san(ai_move))
            self.board.push(ai_move)
            self.last_move = ai_move
            
        self.run_background_analysis()
        
        if self.board.is_game_over():
            self.set_game_over_status()

    def run_background_analysis(self) -> None:
        if not self.engine: return
        def analyze():
            current_fen = self.board.fen()
            data = self.engine.get_fast_analysis(current_fen)
            # Controllo anti-race condition
            if self.board.fen() == current_fen:
                self.current_analysis = data
                if self.game_state != "game_over":
                    self.game_state = "human_turn"
                    self.status_text = f"Tocca a te ({'Bianco' if self.player_color else 'Nero'})"
        
        self.game_state = "analysis_pending"
        threading.Thread(target=analyze, daemon=True).start()

    def set_game_over_status(self) -> None:
        self.game_state = "game_over"
        res = self.board.result()
        if self.board.is_checkmate():
            winner = "Nero" if self.board.turn == chess.WHITE else "Bianco"
            self.status_text = f"Scacco Matto! Vince {winner}."
        else:
            self.status_text = f"Partita finita: {res}"

    def reset_game(self) -> None:
        self.board.reset()
        self.move_history_san.clear()
        self.last_move = None
        self.last_move_info = {"label": "", "color": COLORS.TESTO_SEC, "explanation": "Nuova partita iniziata.", "loss": 0.0}
        
        if self.player_color == chess.BLACK:
            self.game_state = "ai_turn"
            threading.Thread(target=self.process_ai_turn, args=({}, chess.Move.null(), self.board.fen()), daemon=True).start()
        else:
            self.run_background_analysis()

    def undo_move(self) -> None:
        """Annulla l'ultima coppia di mosse (IA + Umano)."""
        if self.game_state not in ["human_turn", "game_over", "analysis_pending"]: return
        
        # 1. Annulla la mossa AI
        if self.board.move_stack:
            self.board.pop()
            if self.move_history_san: self.move_history_san.pop()

        # 2. Annulla la mossa Umana
        if self.board.move_stack:
            self.board.pop()
            if self.move_history_san: self.move_history_san.pop()
            
        # 3. Aggiorna lo stato e l'analisi
        self.last_move = self.board.peek() if self.board.move_stack else None
        
        self.last_move_info = {"label": "", "color": COLORS.TESTO_SEC, "explanation": "Mossa annullata. In attesa di analisi.", "loss": 0.0}
        self.run_background_analysis()  