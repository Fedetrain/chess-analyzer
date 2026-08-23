"""The in-app trainer mode, driven headlessly.

Covers the roadmap's acceptance criterion for the trainer screen: enter trainer
mode, render, play a wrong move, get a refutation and a replay of the line --
and the regression requirement that ordinary play against the engine still
works afterwards.
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import chess
import pygame
import pytest

from engine import EMPTY_ANALYSIS
from repertoire import Repertoire


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    """An isolated data directory, so tests never touch a real profile."""
    path = tmp_path_factory.mktemp("study_data")
    rep = Repertoire(name="Ruy", color=chess.WHITE)
    rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4")
    rep.save(str(path / "repertoire_white.json"))
    return str(path)


@pytest.fixture(scope="module")
def game(data_dir, monkeypatch_module):
    import config

    monkeypatch_module.setattr(config, "DATA_DIR", data_dir)
    import game as game_module

    monkeypatch_module.setattr(game_module, "DATA_DIR", data_dir)

    instance = game_module.Game()
    yield instance
    instance.shutdown()
    pygame.quit()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    patch = MonkeyPatch()
    yield patch
    patch.undo()


class TestEnterAndExit:
    def test_starts_outside_trainer(self, game):
        assert not game.training

    def test_enters_trainer_mode(self, game):
        game.toggle_trainer()
        assert game.training, "a repertoire exists, so the trainer must start"
        assert game.session is not None
        assert game.session.scheduler_name == "FSRS-6"

    def test_poses_a_question(self, game):
        assert game.question is not None
        assert game.question.expected.move in game.board.legal_moves

    def test_renders_the_trainer_panel(self, game):
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, game.last_move, None, None,
            EMPTY_ANALYSIS, game.ui,
        )
        assert game.ui.training
        assert game.ui.training_info["scheduler"] == "FSRS-6"


class TestWrongAnswer:
    def test_wrong_move_is_refused_and_explained(self, game):
        question = game.question
        wrong = next(
            m for m in game.board.legal_moves if m.uci() != question.expected.uci
        )
        before = game.board.fen()

        game.handle_drill_move(wrong)

        assert game.board.fen() == before, "a wrong move must not be played on the board"
        assert game.retry_pending, "the student must be asked to replay the line"
        assert question.expected.san in game.coach_text
        assert game.drill_asked == 1
        assert game.drill_correct == 0

    def test_replaying_the_wrong_move_again_is_still_refused(self, game):
        wrong = next(
            m for m in game.board.legal_moves if m.uci() != game.question.expected.uci
        )
        game.handle_drill_move(wrong)
        assert game.retry_pending

    def test_correct_replay_advances(self, game):
        expected = game.question.expected
        game.handle_drill_move(expected.move)
        assert not game.retry_pending

    def test_wrong_answer_is_scheduled_sooner(self, game):
        """The link between the drill and spaced repetition."""
        session = game.session
        cards = session.repertoire.own_moves
        failed = cards[0].card_id
        passed = cards[1].card_id

        from datetime import datetime, timezone

        from trainer import Answer

        now = datetime(2026, 8, 23, tzinfo=timezone.utc)
        session.record(failed, Answer.AGAIN, now)
        session.record(passed, Answer.GOOD, now)
        assert session.due_in(failed, now) < session.due_in(passed, now)


class TestRegression:
    def test_leaving_the_trainer_restores_a_playable_game(self, game):
        game.training = True
        game.toggle_trainer()
        assert not game.training
        assert game.board.fen() == chess.STARTING_FEN
        assert game.question is None

    def test_normal_play_still_works_after_training(self, game):
        """The constraint: training must not break playing."""
        before = game.board.fen()
        game.attempt_move(chess.Move.from_uci("e2e4"))
        assert game.board.fen() != before
        assert game.move_history_san[-1] == "e4"

    def test_renders_normally_after_training(self, game):
        game.sync_ui()
        game.drawing.redraw_all(
            game.board, game.board_orientation, game.last_move, None, None,
            EMPTY_ANALYSIS, game.ui,
        )
        assert not game.ui.training


class TestMissingRepertoire:
    def test_no_repertoire_gives_advice_not_a_crash(self, tmp_path, monkeypatch):
        import game as game_module

        monkeypatch.setattr(game_module, "DATA_DIR", str(tmp_path / "empty"))
        instance = game_module.Game()
        try:
            instance.toggle_trainer()
            assert not instance.training
            assert "tools.study" in instance.coach_text
        finally:
            instance.shutdown()
