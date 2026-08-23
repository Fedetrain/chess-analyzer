# trainer.py
"""Spaced-repetition drilling of a repertoire.

Scheduling uses **FSRS-6** via the ``fsrs`` package (MIT, one runtime
dependency). FSRS is the default scheduler in Anki and measurably outperforms
SM-2, yet essentially every chess trainer surveyed still runs SM-2 -- adopting it
here is a real advantage, not a cosmetic one. See ``SOTA.md`` 2.2.

The dependency is optional. If ``fsrs`` is not installed the trainer falls back
to a small SM-2 scheduler so the app still works, and says which one is active
rather than pretending.

Drilling model
--------------
* A card is one of *your* moves from one position (``position_key|uci``), so
  transpositions share a card automatically.
* The app plays the opponent's replies from the repertoire; you supply yours.
* A wrong answer shows the refutation and replays the line, and FSRS brings the
  position back sooner.
"""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import chess

from repertoire import Repertoire, RepertoireMove

log = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by whichever branch is installed
    from fsrs import Card as FsrsCard
    from fsrs import Rating as FsrsRating
    from fsrs import Scheduler as FsrsScheduler

    FSRS_AVAILABLE = True
except ImportError:  # pragma: no cover
    FSRS_AVAILABLE = False


class Answer(Enum):
    """How the student did on one card."""

    AGAIN = 1     # wrong
    HARD = 2      # right, but slowly or after hesitation
    GOOD = 3      # right
    EASY = 4      # right, instantly


class DrillMode(Enum):
    WHOLE_LINE = "line"        # play the line through from the start
    SINGLE_POSITION = "spot"   # jump straight to the position that is due


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: A never-studied card is due immediately, whenever "now" happens to be. Both
#: schedulers stamp new cards with this rather than with the wall clock, so a
#: fresh card is not accidentally scheduled into the future.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------- schedulers


class _Sm2Scheduler:
    """Fallback scheduler used only when ``fsrs`` is unavailable.

    A plain SM-2. It exists so the trainer degrades instead of failing; FSRS is
    the intended path.
    """

    name = "SM-2 (fallback)"

    @staticmethod
    def new_state() -> dict:
        return {"reps": 0, "interval": 0.0, "ease": 2.5, "due": EPOCH.isoformat()}

    @staticmethod
    def review(state: dict, answer: Answer, now: datetime) -> dict:
        ease = float(state.get("ease", 2.5))
        reps = int(state.get("reps", 0))
        interval = float(state.get("interval", 0.0))

        if answer is Answer.AGAIN:
            reps, interval = 0, 0.0
            ease = max(1.3, ease - 0.2)
        else:
            quality = {Answer.HARD: 3, Answer.GOOD: 4, Answer.EASY: 5}[answer]
            ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
            if reps == 0:
                interval = 1.0
            elif reps == 1:
                interval = 6.0
            else:
                interval = interval * ease
            reps += 1

        due = now + timedelta(days=interval) if interval else now + timedelta(minutes=1)
        return {"reps": reps, "interval": interval, "ease": ease, "due": due.isoformat()}

    @staticmethod
    def due_at(state: dict) -> datetime:
        return datetime.fromisoformat(state["due"])


class _FsrsScheduler:
    """FSRS-6 scheduler."""

    name = "FSRS-6"

    def __init__(self) -> None:
        self._scheduler = FsrsScheduler()

    def new_state(self) -> dict:
        state = FsrsCard().to_dict()
        # FSRS stamps a new card as due "now"; an unstudied card should be due
        # regardless of what the caller considers now.
        state["due"] = EPOCH.isoformat()
        return state

    def review(self, state: dict, answer: Answer, now: datetime) -> dict:
        card = FsrsCard.from_dict(state)
        rating = {
            Answer.AGAIN: FsrsRating.Again,
            Answer.HARD: FsrsRating.Hard,
            Answer.GOOD: FsrsRating.Good,
            Answer.EASY: FsrsRating.Easy,
        }[answer]
        card, _log = self._scheduler.review_card(card, rating, now)
        return card.to_dict()

    @staticmethod
    def due_at(state: dict) -> datetime:
        due = state["due"]
        return datetime.fromisoformat(due) if isinstance(due, str) else due


def make_scheduler():
    """The best scheduler available, preferring FSRS."""
    if FSRS_AVAILABLE:
        return _FsrsScheduler()
    log.warning("fsrs not installed - falling back to SM-2. `pip install fsrs` for FSRS-6.")
    return _Sm2Scheduler()


# -------------------------------------------------------------------- state


@dataclass
class CardStats:
    """Per-card history, kept alongside the scheduler's own state."""

    reviews: int = 0
    lapses: int = 0
    last_answer: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "reviews": self.reviews,
            "lapses": self.lapses,
            "last_answer": self.last_answer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CardStats":
        return cls(
            reviews=int(data.get("reviews", 0)),
            lapses=int(data.get("lapses", 0)),
            last_answer=data.get("last_answer"),
        )


@dataclass
class Question:
    """One drill prompt."""

    board: chess.Board
    expected: RepertoireMove
    line: List[chess.Move] = field(default_factory=list)
    mode: DrillMode = DrillMode.SINGLE_POSITION

    @property
    def card_id(self) -> str:
        return self.expected.card_id


class StudySession:
    """Schedules and grades drills over a repertoire."""

    def __init__(
        self,
        repertoire: Repertoire,
        path: Optional[str] = None,
        scheduler=None,
        rng: Optional[random.Random] = None,
    ):
        self.repertoire = repertoire
        self.path = path
        self.scheduler = scheduler if scheduler is not None else make_scheduler()
        self.rng = rng or random.Random()
        self.states: Dict[str, dict] = {}
        self.stats: Dict[str, CardStats] = {}
        if path and os.path.exists(path):
            self.load(path)

    @property
    def scheduler_name(self) -> str:
        return self.scheduler.name

    # ------------------------------------------------------------ selection

    def _state_for(self, card_id: str) -> dict:
        if card_id not in self.states:
            self.states[card_id] = self.scheduler.new_state()
        return self.states[card_id]

    def due_cards(self, now: Optional[datetime] = None) -> List[RepertoireMove]:
        """Cards whose review time has arrived, soonest first."""
        now = now or _utcnow()
        due: List[Tuple[datetime, RepertoireMove]] = []
        for entry in self.repertoire.own_moves:
            state = self._state_for(entry.card_id)
            when = self.scheduler.due_at(state)
            if when <= now:
                due.append((when, entry))
        due.sort(key=lambda pair: pair[0])
        return [entry for _, entry in due]

    def next_question(
        self,
        mode: DrillMode = DrillMode.WHOLE_LINE,
        now: Optional[datetime] = None,
    ) -> Optional[Question]:
        """Pick the most overdue card and build a prompt for it."""
        due = self.due_cards(now)
        if not due:
            return None
        target = due[0]

        board, line = self._route_to(target)
        if board is None:
            return None
        return Question(board=board, expected=target, line=line, mode=mode)

    def _route_to(
        self, target: RepertoireMove
    ) -> Tuple[Optional[chess.Board], List[chess.Move]]:
        """Find a move sequence from the start that reaches the card's position.

        Needed because a card is keyed by position, not by line: to drill it in
        WHOLE_LINE mode the trainer has to reconstruct *a* way of getting there.
        Breadth-first, so the shortest route wins.
        """
        from collections import deque

        start = chess.Board()
        if self.repertoire.knows(start) is False and not self.repertoire.edges:
            return None, []

        queue = deque([(start, [])])
        seen = set()
        while queue:
            board, path = queue.popleft()
            from openings import position_key

            key = position_key(board)
            if key == target.epd:
                return board, path
            if key in seen or len(path) > 40:
                continue
            seen.add(key)
            for entry in self.repertoire.moves_from(board):
                child = board.copy()
                child.push(entry.move)
                queue.append((child, path + [entry.move]))
        return None, []

    def opponent_reply(self, board: chess.Board) -> Optional[chess.Move]:
        """Choose the opponent's move from the repertoire.

        Weighted by how often the branch appeared on import, so the lines you
        actually face come up more often than rare sidelines.
        """
        options = self.repertoire.opponent_moves_from(board)
        if not options:
            return None
        weights = [max(1, e.weight) for e in options]
        return self.rng.choices(options, weights=weights, k=1)[0].move

    # -------------------------------------------------------------- grading

    def answer(
        self,
        question: Question,
        played: chess.Move,
        now: Optional[datetime] = None,
        hesitated: bool = False,
    ) -> Tuple[bool, dict]:
        """Grade an answer and reschedule the card.

        Returns ``(correct, new_state)``.
        """
        now = now or _utcnow()
        correct = played.uci() == question.expected.uci

        if not correct:
            grade = Answer.AGAIN
        elif hesitated:
            grade = Answer.HARD
        else:
            grade = Answer.GOOD

        return correct, self.record(question.card_id, grade, now)

    def record(self, card_id: str, grade: Answer, now: Optional[datetime] = None) -> dict:
        now = now or _utcnow()
        state = self._state_for(card_id)
        new_state = self.scheduler.review(state, grade, now)
        self.states[card_id] = new_state

        stats = self.stats.setdefault(card_id, CardStats())
        stats.reviews += 1
        stats.last_answer = grade.name
        if grade is Answer.AGAIN:
            stats.lapses += 1

        if self.path:
            self.save(self.path)
        return new_state

    def due_in(self, card_id: str, now: Optional[datetime] = None) -> timedelta:
        now = now or _utcnow()
        return self.scheduler.due_at(self._state_for(card_id)) - now

    # -------------------------------------------------------------- reports

    def progress(self) -> dict:
        """Overall study progress."""
        own = self.repertoire.own_moves
        seen = [e for e in own if e.card_id in self.states and self.stats.get(e.card_id)]
        lapsed = [e for e in seen if self.stats[e.card_id].lapses > 0]
        return {
            "scheduler": self.scheduler_name,
            "total_cards": len(own),
            "studied": len(seen),
            "due_now": len(self.due_cards()),
            "weak_cards": len(lapsed),
            "accuracy": (
                1.0 - sum(self.stats[e.card_id].lapses for e in seen)
                / max(1, sum(self.stats[e.card_id].reviews for e in seen))
            )
            if seen
            else 0.0,
        }

    def weakest(self, limit: int = 5) -> List[Tuple[RepertoireMove, CardStats]]:
        """The cards you get wrong most: where study time should go."""
        scored = [
            (entry, self.stats[entry.card_id])
            for entry in self.repertoire.own_moves
            if entry.card_id in self.stats and self.stats[entry.card_id].lapses > 0
        ]
        scored.sort(key=lambda pair: (-pair[1].lapses, pair[1].reviews))
        return scored[:limit]

    # ---------------------------------------------------------- persistence

    def to_dict(self) -> dict:
        return {
            "scheduler": self.scheduler_name,
            "states": self.states,
            "stats": {k: v.to_dict() for k, v in self.stats.items()},
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, default=str)
        os.replace(tmp, path)

    def load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read study state from %s: %s", path, exc)
            return
        self.states = data.get("states", {})
        self.stats = {
            k: CardStats.from_dict(v) for k, v in data.get("stats", {}).items()
        }
