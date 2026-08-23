"""Win-probability grading: does it reproduce Lichess, and is it outcome-linear?"""

import chess
import pytest

from analysis import (
    CP_CLAMP,
    Grade,
    game_accuracy,
    grade_for_loss,
    move_accuracy,
    phase_of,
    win_percent,
)


class TestWinPercent:
    def test_equal_position_is_fifty(self):
        assert win_percent(0) == pytest.approx(50.0)

    def test_symmetric_about_zero(self):
        for cp in (50, 137, 400, 999):
            assert win_percent(cp) + win_percent(-cp) == pytest.approx(100.0)

    def test_monotonic(self):
        values = [win_percent(cp) for cp in range(-1000, 1001, 50)]
        assert values == sorted(values)

    def test_bounded(self):
        assert 0.0 <= win_percent(-100000) <= 100.0
        assert 0.0 <= win_percent(100000) <= 100.0

    def test_clamped_at_1000_cp(self):
        """Lichess ceils cp at +/-1000; beyond that the curve must be flat."""
        assert win_percent(CP_CLAMP) == pytest.approx(win_percent(50000))

    def test_hundred_centipawns_is_about_nine_points(self):
        """The documented slope near equality."""
        assert win_percent(100) - win_percent(0) == pytest.approx(9.1, abs=0.3)


class TestMoveAccuracy:
    def test_no_loss_scores_exactly_one_hundred(self):
        """The short circuit the public page omits: not losing win% is 100%."""
        assert move_accuracy(60.0, 60.0) == 100.0
        assert move_accuracy(60.0, 72.0) == 100.0

    def test_accuracy_decreases_with_loss(self):
        scores = [move_accuracy(70.0, 70.0 - d) for d in (0, 2, 5, 10, 20, 40)]
        assert scores == sorted(scores, reverse=True)

    def test_bounded(self):
        assert 0.0 <= move_accuracy(90.0, 0.0) <= 100.0

    def test_small_loss_stays_high(self):
        assert move_accuracy(50.0, 48.0) > 90.0

    def test_huge_loss_collapses(self):
        assert move_accuracy(90.0, 10.0) < 10.0


class TestThresholds:
    @pytest.mark.parametrize(
        "loss,expected",
        [
            (0.0, Grade.EXCELLENT),
            (1.5, Grade.EXCELLENT),
            (3.0, Grade.GOOD),
            (5.0, Grade.INACCURACY),
            (9.9, Grade.INACCURACY),
            (10.0, Grade.MISTAKE),
            (14.9, Grade.MISTAKE),
            (15.0, Grade.BLUNDER),
            (60.0, Grade.BLUNDER),
        ],
    )
    def test_lichess_bands(self, loss, expected):
        assert grade_for_loss(loss) is expected

    def test_engine_best_always_best(self):
        assert grade_for_loss(40.0, is_engine_best=True) is Grade.BEST

    def test_error_flag(self):
        assert Grade.BLUNDER.is_error and Grade.MISTAKE.is_error
        assert not Grade.BEST.is_error and not Grade.EXCELLENT.is_error


class TestOutcomeLinearity:
    """The property that motivates the whole module.

    Losing 100 centipawns from equality is a real error; losing the same 100
    from a completely winning position is not. Centipawn thresholds cannot tell
    these apart -- win-probability grading must.
    """

    def test_same_cp_loss_grades_differently(self):
        loss_at_equality = win_percent(0) - win_percent(-100)
        loss_when_winning = win_percent(1000) - win_percent(900)

        assert loss_at_equality > loss_when_winning * 5

        grade_equal = grade_for_loss(loss_at_equality)
        grade_winning = grade_for_loss(loss_when_winning)

        assert grade_equal.is_error
        assert not grade_winning.is_error

    def test_accuracy_reflects_the_same_asymmetry(self):
        near = move_accuracy(win_percent(0), win_percent(-100))
        far = move_accuracy(win_percent(1000), win_percent(900))
        assert far > near


class TestGameAccuracy:
    def test_perfect_game(self):
        assert game_accuracy([100.0] * 10).overall == pytest.approx(100.0)

    def test_harmonic_term_punishes_a_single_blunder(self):
        """A lone disaster must not be averaged away by many perfect moves."""
        clean = game_accuracy([100.0] * 29 + [100.0]).overall
        blundered = game_accuracy([100.0] * 29 + [0.0]).overall
        arithmetic_only = sum([100.0] * 29 + [0.0]) / 30
        assert blundered < clean
        assert blundered < arithmetic_only

    def test_phase_split(self):
        result = game_accuracy(
            [100.0, 90.0, 50.0, 40.0],
            ["opening", "opening", "endgame", "endgame"],
        )
        assert result.by_phase["opening"] == pytest.approx(95.0)
        assert result.by_phase["endgame"] == pytest.approx(45.0)
        assert result.move_count == 4

    def test_empty(self):
        assert game_accuracy([]).move_count == 0


class TestPhaseOf:
    def test_startpos_is_opening(self):
        assert phase_of(chess.Board()) == "opening"

    def test_bare_kings_and_rooks_is_endgame(self):
        board = chess.Board("6k1/8/8/8/8/8/8/R5K1 w - - 0 40")
        for _ in range(20):
            board.push(chess.Move.null())
        assert phase_of(board) == "endgame"
