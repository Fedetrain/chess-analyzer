# review.py
"""Post-game review: grade a saved game and find where it left the repertoire.

This is the piece that ties the rest together. The classifier (:mod:`analysis`),
the plan engine (:mod:`coach`), the opening book (:mod:`openings`) and the
repertoire (:mod:`repertoire`) each answer one question; a review answers the
one the student actually asks -- *what went wrong in this game, and what should
I study next?*

It also closes the loop back into the trainer: the position where you left your
own preparation is exactly the position worth drilling, so ``weak_cards`` can be
fed straight into a :class:`trainer.StudySession`.

Reviewing needs an engine. Without one it still reports the opening, the
structure and the repertoire deviation, and says the grades are unavailable
rather than inventing them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import chess
import chess.pgn

from analysis import GameAccuracy, Judgement, game_accuracy, phase_of
from coach import Coach
from openings import Opening
from repertoire import Repertoire

log = logging.getLogger(__name__)


@dataclass
class Deviation:
    """Where the game left the repertoire."""

    ply: int
    move_number: int
    played: str
    expected: str
    comment: str = ""

    def __str__(self) -> str:
        return (
            f"move {self.move_number}: played {self.played}, "
            f"repertoire says {self.expected}"
        )


@dataclass
class ReviewedMove:
    """One move of the reviewed game."""

    ply: int
    san: str
    color: chess.Color
    judgement: Judgement | None = None
    in_book: bool = False

    @property
    def move_number(self) -> int:
        return self.ply // 2 + 1

    @property
    def accuracy(self) -> float:
        return self.judgement.accuracy if self.judgement else 100.0


@dataclass
class GameReview:
    """The full verdict on a game."""

    moves: list[ReviewedMove] = field(default_factory=list)
    opening: Opening | None = None
    deviation: Deviation | None = None
    accuracy: GameAccuracy = field(default_factory=GameAccuracy)
    engine_available: bool = True
    color_reviewed: chess.Color = chess.WHITE
    last_book_ply: int = 0

    @property
    def blunders(self) -> list[ReviewedMove]:
        return [m for m in self.moves if m.judgement and m.judgement.grade.name == "BLUNDER"]

    @property
    def mistakes(self) -> list[ReviewedMove]:
        return [
            m for m in self.moves
            if m.judgement and m.judgement.grade.name in ("MISTAKE", "BLUNDER")
        ]

    def summary(self) -> str:
        lines = [
            f"Opening        : {self.opening or 'unknown'}",
            f"Left book after: move {self.last_book_ply // 2 + 1}",
        ]
        if self.deviation:
            lines.append(f"Repertoire     : {self.deviation}")
        elif self.deviation is None:
            lines.append("Repertoire     : no deviation found")
        if self.engine_available:
            lines.append(f"Accuracy       : {self.accuracy.overall:.1f}%")
            for phase in ("opening", "middlegame", "endgame"):
                if phase in self.accuracy.by_phase:
                    lines.append(f"  {phase:11}: {self.accuracy.by_phase[phase]:.1f}%")
            lines.append(f"Mistakes       : {len(self.mistakes)} ({len(self.blunders)} blunders)")
        else:
            lines.append("Accuracy       : unavailable (no engine configured)")
        return "\n".join(lines)


class Reviewer:
    """Reviews games, with or without an engine."""

    def __init__(self, engine=None, coach: Coach | None = None, depth: int = 12):
        self.engine = engine
        self.coach = coach or Coach()
        self.depth = depth

    def review_moves(
        self,
        moves: list[chess.Move],
        color: chess.Color = chess.WHITE,
        rep: Repertoire | None = None,
    ) -> GameReview:
        """Review a move list, grading only *color*'s moves."""
        engine_ok = self.engine is not None and getattr(self.engine, "is_ready", False)
        review = GameReview(engine_available=engine_ok, color_reviewed=color)

        board = chess.Board()
        accuracies: list[float] = []
        phases: list[str] = []
        still_in_book = True

        for ply, move in enumerate(moves):
            if move not in board.legal_moves:
                log.warning("Illegal move at ply %d, stopping review.", ply)
                break

            before = board.copy()
            entry = ReviewedMove(ply=ply, san=board.san(move), color=board.turn)

            if board.turn == color and engine_ok:
                analysis_before = self.engine.analyse(before, depth=self.depth)
                after = before.copy()
                after.push(move)
                analysis_after = self.engine.analyse(after, depth=self.depth)
                judgement = self.engine.classify_move(
                    before, move, analysis_before, analysis_after
                )
                self.coach.annotate(judgement, before, move)
                entry.judgement = judgement
                entry.in_book = judgement.is_book
                accuracies.append(judgement.accuracy)
                phases.append(phase_of(before))

            board.push(move)

            if still_in_book and self.coach.book.lookup(board) is not None:
                review.last_book_ply = ply
            elif self.coach.book.lookup(board) is None:
                still_in_book = False

            review.moves.append(entry)

        review.opening = self.coach.book.identify(board)
        review.accuracy = game_accuracy(accuracies, phases)

        if rep is not None:
            found = rep.find_deviation(moves)
            if found is not None:
                dev_ply, played, expected = found
                replay = chess.Board()
                for m in moves[:dev_ply]:
                    replay.push(m)
                review.deviation = Deviation(
                    ply=dev_ply,
                    move_number=dev_ply // 2 + 1,
                    played=replay.san(played),
                    expected=expected.san,
                    comment=expected.comment,
                )

        return review

    def review_game(
        self,
        game: chess.pgn.Game,
        color: chess.Color = chess.WHITE,
        rep: Repertoire | None = None,
    ) -> GameReview:
        return self.review_moves(list(game.mainline_moves()), color=color, rep=rep)

    def review_pgn(
        self,
        path: str,
        color: chess.Color = chess.WHITE,
        rep: Repertoire | None = None,
    ) -> list[GameReview]:
        reviews: list[GameReview] = []
        with open(path, encoding="utf-8", errors="replace") as handle:
            while (game := chess.pgn.read_game(handle)) is not None:
                reviews.append(self.review_game(game, color=color, rep=rep))
        return reviews


def suggest_study(review: GameReview) -> list[str]:
    """Turn a review into concrete study advice.

    Ordered by how much the mistake cost, because that is the order in which
    fixing them pays.
    """
    advice: list[str] = []

    if review.deviation is not None:
        advice.append(
            f"Revise your repertoire at move {review.deviation.move_number}: "
            f"you played {review.deviation.played}, your line is "
            f"{review.deviation.expected}."
        )

    ranked = sorted(
        (m for m in review.moves if m.judgement and m.judgement.grade.is_error),
        key=lambda m: -m.judgement.win_loss,
    )
    for entry in ranked[:3]:
        judgement = entry.judgement
        advice.append(
            f"Move {entry.move_number} {entry.san} ({judgement.label}, "
            f"-{judgement.win_loss:.0f}% winning chances): {judgement.best_san} was better."
        )

    if review.engine_available and review.accuracy.by_phase:
        worst = min(review.accuracy.by_phase.items(), key=lambda kv: kv[1])
        advice.append(f"Weakest phase: {worst[0]} at {worst[1]:.0f}% accuracy.")

    if not advice:
        advice.append("No significant errors found in this game.")
    return advice
