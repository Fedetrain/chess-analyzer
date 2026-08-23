# game.py
import pygame
import chess
import os
import threading
from typing import Optional, Dict, Any, Tuple, List
import time

from analysis import Judgement, phase_of
from coach import Coach
from openings import get_book
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, STOCKFISH_PATH, ASSET_PATH,
    BOARD_SIZE, SQUARE_SIZE, DEFAULT_ELO_INDEX, ELO_LEVELS,
    PGN_PATH, COLORS, DATA_DIR
)
from repertoire import Repertoire
from trainer import DrillMode, StudySession
from engine import EMPTY_ANALYSIS, Analysis, EngineWrapper
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
    
class Game:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            # No audio device (CI, headless, locked device). Sound is optional;
            # failing to open a mixer must never stop the app from starting.
            pass

        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Chess Analyzer")

        self.clock = pygame.time.Clock()
        self.asset_manager = AssetManager()
        self.piece_images = self.asset_manager.load_piece_images()
        
        # Game State
        self.board = chess.Board()
        self.move_history_san: List[str] = []
        self.selected_square: Optional[int] = None
        self.dragging_piece: Optional[Tuple[pygame.Surface, pygame.Rect]] = None
        
        self.player_color = chess.WHITE
        self.board_orientation = chess.WHITE
        self.last_move: Optional[chess.Move] = None
        self.current_elo = ELO_LEVELS[DEFAULT_ELO_INDEX]
        
        # Analysis state
        self.current_analysis: Analysis = EMPTY_ANALYSIS
        self.last_judgement: Optional[Judgement] = None
        self.coach_text = "Play a move to get feedback."
        self.accuracies: List[float] = []
        self.phases: List[str] = []

        # Trainer state
        self.training = False
        self.training_info: Dict[str, Any] = {}
        self.session: Optional[StudySession] = None
        self.question = None
        self.drill_correct = 0
        self.drill_asked = 0
        self.retry_pending = False

        self.game_state = "loading"
        self.status_text = "Starting engine..."
        
        # Components
        self.engine: Optional[EngineWrapper] = None
        self.drawing = Drawing(self.screen, self.piece_images)
        self.pgn_handler = PGNHandler()
        self.openings = get_book()
        self.coach = Coach(book=self.openings)

        os.makedirs(PGN_PATH, exist_ok=True)

        self.ui = UIManager()
        self.ui.current_elo = self.current_elo

        self.engine_thread = threading.Thread(target=self.init_engine, args=(STOCKFISH_PATH,), daemon=True)
        self.engine_thread.start()

    def init_engine(self, path: Optional[str]) -> None:
        self.engine = EngineWrapper(path, elo=self.current_elo)
        if not self.engine.is_ready:
            self.game_state = "no_engine"
            self.status_text = "No engine - set STOCKFISH_PATH"
            return
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
            
            self.sync_ui()
            self.drawing.redraw_all(
                self.board, self.board_orientation, self.last_move,
                self.selected_square, self.dragging_piece,
                self.current_analysis, self.ui
            )

            self.clock.tick(60)

        self.shutdown()

    def sync_ui(self) -> None:
        """Push game state into the UI layer. The UI owns no game state itself."""
        self.ui.update_state(
            game_state=self.game_state,
            status_text=self.status_text,
            judgement=self.last_judgement,
            coach_text=self.coach_text,
            current_analysis=self.current_analysis,
            player_color=self.player_color,
            move_history_san=self.move_history_san,
            opening_name=self.opening_name,
            accuracy=self.session_accuracy,
            training=self.training,
            training_info=self.training_info,
        )

    def shutdown(self) -> None:
        """Release the engine subprocess. Without this the UCI child can outlive
        the GUI and keep a core busy."""
        if self.engine is not None:
            self.engine.close()

    @property
    def opening_name(self) -> str:
        return self.openings.describe(self.board)

    @property
    def session_accuracy(self) -> float:
        from analysis import game_accuracy
        return game_accuracy(self.accuracies).overall if self.accuracies else 0.0

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
        elif action == "train":
            self.toggle_trainer()
        elif action == "undo":
            if not self.training:
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
        if move not in self.board.legal_moves:
            self.selected_square = None
            return

        if self.training:
            self.handle_drill_move(move)
            self.selected_square = None
            return

        board_before = self.board.copy()

        self.move_history_san.append(self.board.san(move))
        self.board.push(move)
        self.last_move = move

        # Snapshot the resulting position: the grading thread must evaluate
        # exactly this one, not "the current board", which by then may already
        # contain the engine's reply.
        board_after = self.board.copy()

        self.game_state = "ai_turn"
        self.status_text = "Analysing your move..."

        threading.Thread(
            target=self.process_ai_turn,
            args=(board_before, move, board_after),
            daemon=True,
        ).start()

    def process_ai_turn(
        self,
        board_before: Optional[chess.Board],
        human_move: Optional[chess.Move],
        board_after: Optional[chess.Board],
    ) -> None:
        if not self.engine or not self.engine.is_ready:
            return

        if human_move is not None and board_before is not None:
            self.grade_human_move(board_before, human_move, board_after)

        if self.board.is_game_over():
            self.set_game_over_status()
            return

        ai_move = self.engine.play(self.board)
        if ai_move and ai_move in self.board.legal_moves:
            self.move_history_san.append(self.board.san(ai_move))
            self.board.push(ai_move)
            self.last_move = ai_move

        if self.board.is_game_over():
            self.set_game_over_status()
            return

        self.run_background_analysis()

    def grade_human_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        board_after: Optional[chess.Board],
    ) -> None:
        """Grade one human move and hand the result to the coach.

        The pre-move analysis may be stale (the background worker writes it, and
        a fast player can move before it lands), so it is re-derived whenever it
        does not describe the position the move was actually played from.
        """
        analysis_before = self.current_analysis
        if analysis_before.fen != board_before.fen():
            analysis_before = self.engine.analyse(board_before)

        analysis_after = (
            self.engine.analyse(board_after) if board_after is not None else EMPTY_ANALYSIS
        )

        judgement = self.engine.classify_move(
            board_before, move, analysis_before, analysis_after
        )
        judgement.opening = self.opening_name
        self.coach.annotate(judgement, board_before, move)

        self.last_judgement = judgement
        self.coach_text = judgement.explanation
        self.accuracies.append(judgement.accuracy)
        self.phases.append(phase_of(board_before))

    def run_background_analysis(self) -> None:
        if not self.engine or not self.engine.is_ready:
            return

        def analyze():
            board_snapshot = self.board.copy()
            data = self.engine.analyse(board_snapshot)
            # Only publish if the board still holds the analysed position, and
            # only if we are still playing: a search started before the user
            # entered the trainer would otherwise land afterwards and overwrite
            # the drill's own status line.
            if self.board.fen() == data.fen and not self.training:
                self.current_analysis = data
                if self.game_state != "game_over":
                    self.game_state = "human_turn"
                    side = "White" if self.player_color == chess.WHITE else "Black"
                    self.status_text = f"Your turn ({side})"

        self.game_state = "analysis_pending"
        threading.Thread(target=analyze, daemon=True).start()

    def set_game_over_status(self) -> None:
        self.game_state = "game_over"
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self.status_text = f"Checkmate - {winner} wins"
        else:
            self.status_text = f"Game over: {self.board.result()}"

    # ------------------------------------------------------------- trainer

    def toggle_trainer(self) -> None:
        """Enter or leave repertoire drilling."""
        if self.training:
            self.training = False
            self.question = None
            self.retry_pending = False
            self.reset_game()
            self.status_text = "Back to playing."
            return

        rep_path = os.path.join(
            DATA_DIR,
            "repertoire_white.json" if self.player_color == chess.WHITE else "repertoire_black.json",
        )
        if not os.path.exists(rep_path):
            self.coach_text = (
                "No repertoire found. Build one first, e.g.\n"
                "python -m tools.study build --color white --line \"e4 e5 Nf3\""
            )
            self.status_text = "No repertoire to train"
            return

        try:
            rep = Repertoire.load(rep_path)
        except (OSError, ValueError, KeyError) as exc:
            self.coach_text = f"Could not read the repertoire: {exc}"
            return

        if not rep.own_moves:
            self.coach_text = "That repertoire has no moves of your own to drill."
            return

        study_path = os.path.join(
            DATA_DIR,
            "study_white.json" if self.player_color == chess.WHITE else "study_black.json",
        )
        self.session = StudySession(rep, path=study_path)
        self.training = True
        self.drill_correct = self.drill_asked = 0
        self.last_judgement = None
        self.next_drill()

    def next_drill(self) -> None:
        """Load the next due position, or report that the queue is empty."""
        if not self.session:
            return

        self.retry_pending = False
        self.question = self.session.next_question(mode=DrillMode.WHOLE_LINE)

        if self.question is None:
            self.status_text = "Nothing due - all caught up"
            self.coach_text = "Every position in this repertoire is scheduled for later."
            self.board = chess.Board()
            self.move_history_san = []
            self.last_move = None
            self.update_training_info("")
            return

        self.board = self.question.board.copy()
        self.move_history_san = self._san_history(self.question.line)
        self.last_move = self.board.peek() if self.board.move_stack else None
        self.board_orientation = self.player_color
        self.selected_square = None
        self.game_state = "human_turn"
        self.status_text = "Your move (from the repertoire)"
        self.coach_text = "Play the move your repertoire says. Take your time."
        self.current_analysis = EMPTY_ANALYSIS
        self.update_training_info("Which move does your repertoire play here?")

    @staticmethod
    def _san_history(moves: List[chess.Move]) -> List[str]:
        board = chess.Board()
        out: List[str] = []
        for move in moves:
            out.append(board.san(move))
            board.push(move)
        return out

    def update_training_info(self, prompt: str) -> None:
        if not self.session:
            return
        progress = self.session.progress()
        self.training_info = {
            "scheduler": progress["scheduler"],
            "due_now": progress["due_now"],
            "total_cards": progress["total_cards"],
            "correct": self.drill_correct,
            "asked": self.drill_asked,
            "prompt": prompt,
        }

    def handle_drill_move(self, move: chess.Move) -> None:
        """Check a drilled move, and on a miss show why it fails."""
        if not (self.session and self.question):
            return

        if self.retry_pending:
            # The student is replaying the line after a miss.
            if move.uci() == self.question.expected.uci:
                self.board.push(move)
                self.last_move = move
                self.move_history_san.append(self.question.expected.san)
                self.coach_text = "Right. That is the move."
                self.status_text = "Correct - next position"
                self.next_drill()
            else:
                self.coach_text = f"Not yet. The move is {self.question.expected.san}."
            return

        correct, _ = self.session.answer(self.question, move)
        self.drill_asked += 1

        board_before = self.question.board.copy()
        expected = self.question.expected

        if correct:
            self.drill_correct += 1
            self.board.push(move)
            self.last_move = move
            self.move_history_san.append(expected.san)

            after = board_before.copy()
            after.push(expected.move)
            briefing = self.coach.brief(after)
            plans = briefing.plans_for(board_before.turn)
            self.coach_text = (
                f"Correct: {expected.san}. "
                + (f"Idea: {plans[0]}" if plans else "")
            )
            self.status_text = "Correct"
            self.update_training_info("")
            threading.Thread(target=self._advance_after_correct, daemon=True).start()
        else:
            self.status_text = "Not the repertoire move"
            self.coach_text = self._refutation(board_before, move, expected)
            self.retry_pending = True
            self.update_training_info(f"Play {expected.san} to continue.")

    def _advance_after_correct(self) -> None:
        """Play the opponent's reply, then pose the next question."""
        time.sleep(0.6)
        reply = self.session.opponent_reply(self.board) if self.session else None
        if reply is not None and reply in self.board.legal_moves:
            self.move_history_san.append(self.board.san(reply))
            self.board.push(reply)
            self.last_move = reply
            time.sleep(0.4)
        self.next_drill()

    def _refutation(self, board_before, played, expected) -> str:
        """Explain why the played move is not the repertoire move.

        With an engine available this is a real refutation: what the opponent
        gets to do about it. Without one it still names the expected move, and
        says the engine is unavailable rather than bluffing.
        """
        try:
            san_played = board_before.san(played)
        except (ValueError, AssertionError):
            san_played = played.uci()

        base = f"You played {san_played}; the repertoire move is {expected.san}."
        if expected.comment:
            base += f" {expected.comment}"

        if not (self.engine and self.engine.is_ready):
            return base + " (No engine configured, so no refutation to show.)"

        after = board_before.copy()
        after.push(played)
        analysis = self.engine.analyse(after, depth=12)
        if analysis.best is None:
            return base

        punish = after.san(analysis.best.move)
        mover = board_before.turn
        cp = analysis.score_white if mover == chess.WHITE else -analysis.score_white
        return f"{base} The refutation is {punish}, leaving you at {cp / 100:+.2f}."

    def reset_game(self) -> None:
        self.board.reset()
        self.move_history_san.clear()
        self.last_move = None
        self.last_judgement = None
        self.current_analysis = EMPTY_ANALYSIS
        self.coach_text = "New game. Play a move to get feedback."
        self.accuracies.clear()
        self.phases.clear()

        if self.player_color == chess.BLACK:
            self.game_state = "ai_turn"
            threading.Thread(
                target=self.process_ai_turn, args=(None, None, None), daemon=True
            ).start()
        else:
            self.run_background_analysis()

    def undo_move(self) -> None:
        """Roll back the human/engine move pair and re-run the analysis."""
        if self.game_state not in ("human_turn", "game_over", "analysis_pending", "no_engine"):
            return

        for _ in range(2):
            if self.board.move_stack:
                self.board.pop()
                if self.move_history_san:
                    self.move_history_san.pop()

        # Drop the grade that belonged to the move just taken back, so the
        # panel cannot keep showing a verdict on a move that no longer exists.
        if self.accuracies:
            self.accuracies.pop()
        if self.phases:
            self.phases.pop()

        self.last_move = self.board.peek() if self.board.move_stack else None
        self.last_judgement = None
        self.coach_text = "Move taken back."
        self.run_background_analysis()