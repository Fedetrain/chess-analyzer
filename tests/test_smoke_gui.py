"""Headless GUI smoke tests.

These run with SDL's dummy video/audio drivers, so they exercise the real
pygame render path with no window and no sound device -- which is also how CI
runs them. They are the regression net for "the app still starts, renders, and
accepts a move" after changes to the engine or analysis layers.

They deliberately do NOT require an engine binary: the GUI must remain usable
(and must not crash) when no engine is configured.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import chess
import pygame
import pytest

from analysis import Judgement
from engine import EMPTY_ANALYSIS, Analysis, MoveCandidate


@pytest.fixture(scope="module")
def game():
    from game import Game

    instance = Game()
    yield instance
    instance.shutdown()
    pygame.quit()


class TestStartup:
    def test_window_is_created(self, game):
        assert game.screen.get_size() == (1144, 720)

    def test_board_starts_at_the_initial_position(self, game):
        assert game.board.fen() == chess.STARTING_FEN

    def test_opening_name_available(self, game):
        assert game.opening_name


class TestRendering:
    def test_renders_a_frame_without_analysis(self, game):
        """The no-engine path must still paint a complete frame."""
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, None, None, None, EMPTY_ANALYSIS, game.ui
        )

    def test_renders_a_frame_with_analysis(self, game):
        analysis = Analysis(
            fen=game.board.fen(),
            depth=12,
            candidates=[
                MoveCandidate(
                    move=chess.Move.from_uci("e2e4"),
                    score_white=42,
                    score_relative=42,
                    pv=[chess.Move.from_uci("e2e4")],
                )
            ],
            score_white=42,
        )
        game.current_analysis = analysis
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, None, None, None, analysis, game.ui
        )

    def test_renders_a_mate_score(self, game):
        """A mate used to be read as a centipawn value and drew a bar at parity."""
        analysis = Analysis(
            fen=game.board.fen(), depth=12,
            candidates=[
                MoveCandidate(
                    move=chess.Move.from_uci("e2e4"),
                    score_white=9800, score_relative=9800,
                    pv=[chess.Move.from_uci("e2e4")], mate_in=2,
                )
            ],
            score_white=9800, mate_in=2,
        )
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, None, None, None, analysis, game.ui
        )

    def test_renders_with_a_judgement(self, game):
        board = chess.Board()
        move = board.parse_san("e4")
        judgement = Judgement(move=move, san="e4")
        game.coach.annotate(judgement, board, move)
        game.last_judgement = judgement
        game.coach_text = judgement.explanation
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, None, None, None, EMPTY_ANALYSIS, game.ui
        )

    def test_renders_flipped(self, game):
        game.drawing.redraw_all(
            game.board, chess.BLACK, None, None, None, EMPTY_ANALYSIS, game.ui
        )


class TestInteraction:
    def test_square_from_position_round_trips(self, game):
        game.board_orientation = chess.WHITE
        assert game.get_square_from_pos((45, 675)) == chess.A1
        assert game.get_square_from_pos((45, 45)) == chess.A8

    def test_flip_changes_mapping(self, game):
        game.board_orientation = chess.BLACK
        assert game.get_square_from_pos((45, 675)) == chess.H8
        game.board_orientation = chess.WHITE

    def test_illegal_move_is_rejected(self, game):
        before = game.board.fen()
        game.attempt_move(chess.Move.from_uci("e2e5"))
        assert game.board.fen() == before

    def test_promotion_is_auto_queened(self, game):
        board = chess.Board("8/P7/8/8/8/8/8/K6k w - - 0 1")
        game.board = board
        move = game.create_move(chess.A7, chess.A8)
        assert move.promotion == chess.QUEEN
        game.board = chess.Board()


class TestSliderStops:
    def test_every_stop_maps_to_a_real_configuration(self):
        """The slider used to claim 800 and 3200, neither of which existed."""
        from config import ELO_LEVELS, UCI_ELO_MIN, strength_for_elo

        descriptions = set()
        for elo in ELO_LEVELS:
            profile = strength_for_elo(elo)
            descriptions.add(profile.description)
            if elo < UCI_ELO_MIN:
                assert not profile.use_uci_elo
                assert profile.node_limit          # weakness needs a node cap
            else:
                assert profile.use_uci_elo
                assert UCI_ELO_MIN <= profile.uci_elo <= 3190

        assert len(descriptions) == len(ELO_LEVELS), "stops must be distinguishable"
