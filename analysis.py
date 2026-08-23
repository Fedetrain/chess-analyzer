# analysis.py
"""Move grading in win-probability space.

Why not centipawn thresholds
----------------------------
The centipawn scale is not linear in *outcome*. Mapping it to a win percentage
first is what makes a grade mean the same thing everywhere on the board:

* 0 cp -> -100 cp costs about 9 points of win probability.
* +900 cp -> +1000 cp costs about 1 point.

A rule like "100 centipawns lost is a mistake" therefore punishes both equally,
even though the second changed essentially nothing about the likely result. Loss
measured in win percentage is outcome-linear, naturally bounded, and lets per-move
accuracy be averaged into a game score.

The formulas are Lichess's, reproduced from the primary sources rather than from
the public summary page, which omits three details implemented here: the ``+1``
uncertainty bonus, the exact-100 short circuit when a move loses no win
probability, and the clamp to [0, 100].

* ``WinPercent.scala``  - https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/WinPercent.scala
* ``AccuracyPercent.scala`` - https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/AccuracyPercent.scala
* ``Advice.scala`` (judgement thresholds) - https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/Advice.scala
* Public summary - https://lichess.org/page/accuracy

chess.com's CAPS2 is deliberately not reproduced: the formula is unpublished, so
any "CAPS" number here would be an invented figure wearing someone else's name.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

import chess

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, types only
    from engine import Analysis

# Lichess constants, verbatim from the sources above.
_WIN_MULTIPLIER = -0.00368208
_ACC_A = 103.1668100711649
_ACC_B = -0.04354415386753951
_ACC_C = -3.166924740191411
_ACC_BONUS = 1.0

#: Lichess ceils centipawn values at +/- 1000 before converting to win percent.
CP_CLAMP = 1000

#: Judgement thresholds in win-percentage points (Advice.scala uses winning
#: chances in [-1, 1], where 0.1 / 0.2 / 0.3 correspond to 5 / 10 / 15 points).
THRESHOLD_INACCURACY = 5.0
THRESHOLD_MISTAKE = 10.0
THRESHOLD_BLUNDER = 15.0


def win_percent(cp: float) -> float:
    """Convert a centipawn score into a win percentage in [0, 100].

    *cp* must already be expressed from the point of view of the player whose
    chances are being measured.
    """
    cp = max(-CP_CLAMP, min(CP_CLAMP, cp))
    chances = 2 / (1 + math.exp(_WIN_MULTIPLIER * cp)) - 1
    chances = max(-1.0, min(1.0, chances))
    return 50 + 50 * chances


def move_accuracy(win_before: float, win_after: float) -> float:
    """Accuracy of a single move, in [0, 100].

    A move that does not reduce the mover's win percentage scores exactly 100 --
    an engine's second choice is not automatically an imperfection.
    """
    if win_after >= win_before:
        return 100.0
    delta = win_before - win_after
    raw = _ACC_A * math.exp(_ACC_B * delta) + _ACC_C + _ACC_BONUS
    return max(0.0, min(100.0, raw))


class Grade(Enum):
    """Move grades, ordered from best to worst."""

    BEST = "Best"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"
    BLUNDER = "Blunder"
    BOOK = "Book"

    @property
    def is_error(self) -> bool:
        return self in (Grade.INACCURACY, Grade.MISTAKE, Grade.BLUNDER)


def grade_for_loss(win_loss: float, *, is_engine_best: bool = False) -> Grade:
    """Grade a move from its win-percentage loss."""
    if is_engine_best:
        return Grade.BEST
    if win_loss >= THRESHOLD_BLUNDER:
        return Grade.BLUNDER
    if win_loss >= THRESHOLD_MISTAKE:
        return Grade.MISTAKE
    if win_loss >= THRESHOLD_INACCURACY:
        return Grade.INACCURACY
    if win_loss >= 2.0:
        return Grade.GOOD
    return Grade.EXCELLENT


@dataclass
class Judgement:
    """The full verdict on one played move."""

    move: chess.Move
    san: str = ""
    grade: Grade = Grade.EXCELLENT
    win_loss: float = 0.0          # win-percentage points given away
    accuracy: float = 100.0        # 0..100
    cp_loss: int = 0               # kept for display; not used for grading
    win_before: float = 50.0
    win_after: float = 50.0
    best_move: Optional[chess.Move] = None
    best_san: str = ""
    explanation: str = ""
    plan: Optional[object] = None  # PositionBriefing, filled in by the coach
    is_book: bool = False
    opening: str = ""

    @property
    def label(self) -> str:
        return Grade.BOOK.value if self.is_book else self.grade.value


def classify(
    board_before: chess.Board,
    move: chess.Move,
    analysis_before: "Analysis",
    analysis_after: "Analysis",
) -> Judgement:
    """Grade *move* by comparing the position before and after it.

    Both evaluations are pulled into White's frame via ``PovScore.white()`` and
    then flipped once into the mover's frame, so the comparison can never end up
    straddling two frames of reference -- the failure mode that made the old
    centipawn code negate one score by hand and the eval bar negate neither.
    """
    mover = board_before.turn
    san = board_before.san(move) if move in board_before.legal_moves else move.uci()

    judgement = Judgement(move=move, san=san)
    if analysis_before is None or analysis_before.is_empty:
        return judgement

    def to_mover(cp_white: int) -> int:
        return cp_white if mover == chess.WHITE else -cp_white

    best = analysis_before.best
    cp_best = to_mover(best.score_white)

    if analysis_after is not None and not analysis_after.is_empty:
        cp_actual = to_mover(analysis_after.score_white)
    else:
        # Without a post-move evaluation the best we can honestly say is that the
        # move matched, or did not match, the engine's own choice.
        cp_actual = cp_best if best.move == move else cp_best

    judgement.win_before = win_percent(cp_best)
    judgement.win_after = win_percent(cp_actual)
    judgement.win_loss = max(0.0, judgement.win_before - judgement.win_after)
    judgement.cp_loss = max(0, cp_best - cp_actual)
    judgement.accuracy = move_accuracy(judgement.win_before, judgement.win_after)
    judgement.best_move = best.move
    try:
        judgement.best_san = board_before.san(best.move)
    except (ValueError, AssertionError):
        judgement.best_san = best.move.uci()

    judgement.grade = grade_for_loss(
        judgement.win_loss, is_engine_best=(best.move == move)
    )
    return judgement


# --------------------------------------------------------------------- games


@dataclass
class GameAccuracy:
    """Accuracy of a whole game, split by phase."""

    overall: float = 0.0
    by_phase: Dict[str, float] = field(default_factory=dict)
    move_count: int = 0


def _harmonic_mean(values: Sequence[float]) -> float:
    safe = [max(v, 1e-6) for v in values]
    return len(safe) / sum(1.0 / v for v in safe)


def game_accuracy(accuracies: Sequence[float], phases: Optional[Sequence[str]] = None) -> GameAccuracy:
    """Aggregate per-move accuracies into a game score.

    Lichess averages a volatility-weighted mean with a harmonic mean; the
    harmonic mean is what stops a single blunder from being averaged away by a
    long tail of forced recaptures. The volatility weighting needs the full win
    percentage series, so when it is unavailable this uses the plain mean as the
    first term -- documented here rather than silently approximated.
    """
    if not accuracies:
        return GameAccuracy()

    arithmetic = sum(accuracies) / len(accuracies)
    harmonic = _harmonic_mean(accuracies)
    overall = (arithmetic + harmonic) / 2

    by_phase: Dict[str, float] = {}
    if phases:
        buckets: Dict[str, List[float]] = {}
        for acc, phase in zip(accuracies, phases):
            buckets.setdefault(phase, []).append(acc)
        for phase, vals in buckets.items():
            by_phase[phase] = sum(vals) / len(vals)

    return GameAccuracy(overall=overall, by_phase=by_phase, move_count=len(accuracies))


def phase_of(board: chess.Board) -> str:
    """Classify the game phase, for per-phase accuracy reporting."""
    if len(board.move_stack) < 20:
        return "opening"
    officers = sum(
        len(board.pieces(pt, color))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for color in (chess.WHITE, chess.BLACK)
    )
    return "endgame" if officers <= 6 else "middlegame"
