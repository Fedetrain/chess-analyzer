# coach.py
"""The "why": plans, not just numbers.

An evaluation says *how much*. This module answers *why*, and it does so without
inventing anything. Three sources, in strict order of trustworthiness:

1. **Computed from the board** (:mod:`structures`) -- the pawn structure, half-open
   files, outposts, backward pawns, bad bishops. Arithmetic; always available;
   cannot be wrong.
2. **Curated knowledge** (``data/plans/structures.json``) -- typical plans keyed by
   *structure* rather than by opening name, so one entry serves every ECO code
   that reaches it. Hand-authored and versioned, declared as such.
3. **Optional enrichment** -- a Wikibooks deep link derived mechanically from the
   move sequence, and opening statistics if the online explorer is enabled.
   Both are strictly additive and never on the critical path.

There is deliberately no LLM in this pipeline. Research measured 22-40% incorrect
sub-claims in LLM chess commentary (ACT-Eval, arXiv 2608.04240, 2026-08-04), so
an LLM may only ever verbalise concepts the engine and the board have already
established -- never supply them. See ``SOTA.md`` 2.5.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional

import chess

from analysis import Grade, Judgement
from openings import Opening, OpeningBook, get_book
from structures import Structure, StructureReport, analyse_structure

log = logging.getLogger(__name__)

PLANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "plans")

WIKIBOOKS_ROOT = "https://en.wikibooks.org/wiki/Chess_Opening_Theory"


@dataclass
class PositionBriefing:
    """Everything the coach can say about a position, with its provenance."""

    structure_name: str = ""
    summary: str = ""
    plans_white: List[str] = field(default_factory=list)
    plans_black: List[str] = field(default_factory=list)
    good_pieces: List[str] = field(default_factory=list)
    bad_pieces: List[str] = field(default_factory=list)
    typical_mistakes: List[str] = field(default_factory=list)
    traps: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    opening: Optional[Opening] = None
    study_url: str = ""

    def plans_for(self, color: chess.Color) -> List[str]:
        return self.plans_white if color == chess.WHITE else self.plans_black

    @property
    def is_empty(self) -> bool:
        return not (self.summary or self.observations)


def wikibooks_url(board: chess.Board) -> str:
    """Build the Wikibooks *Chess Opening Theory* URL for this line.

    Wikibooks encodes the move sequence directly in the path
    (``/1._e4/1...c5/2._Nf3``), so the page for the current position is
    derivable with no network call and no lookup table. The link is offered,
    not fetched -- the app never blocks on it.
    """
    if not board.move_stack:
        return WIKIBOOKS_ROOT

    replay = chess.Board()
    segments: List[str] = []
    for index, move in enumerate(board.move_stack[:12]):
        san = replay.san(move)
        number = index // 2 + 1
        segments.append(f"{number}._{san}" if index % 2 == 0 else f"{number}...{san}")
        replay.push(move)

    path = "/".join(urllib.parse.quote(s) for s in segments)
    return f"{WIKIBOOKS_ROOT}/{path}"


class PlanLibrary:
    """The curated structure -> plans knowledge base."""

    def __init__(self, directory: str = PLANS_DIR):
        self.structures = self._load(os.path.join(directory, "structures.json"))

    @staticmethod
    def _load(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Plan library unavailable (%s): %s", path, exc)
            return {}

    def for_structure(self, structure: Structure) -> dict:
        return self.structures.get(str(structure), {})


class Coach:
    """Turns a position, and a graded move, into an explanation of the ideas."""

    def __init__(
        self,
        book: Optional[OpeningBook] = None,
        library: Optional[PlanLibrary] = None,
    ):
        self.book = book if book is not None else get_book()
        self.library = library if library is not None else PlanLibrary()

    # ------------------------------------------------------------ briefing

    def brief(self, board: chess.Board) -> PositionBriefing:
        """Explain the position: structure, plans for both sides, weaknesses."""
        report = analyse_structure(board)
        entry = self.library.for_structure(report.structure)

        briefing = PositionBriefing(
            structure_name=report.name,
            summary=entry.get("summary", ""),
            good_pieces=list(entry.get("good_pieces", [])),
            bad_pieces=list(entry.get("bad_pieces", [])),
            typical_mistakes=list(entry.get("typical_mistakes", [])),
            traps=list(entry.get("traps", [])),
            opening=self.book.identify(board),
            study_url=wikibooks_url(board),
        )

        # The JSON is written from the feature owner's point of view, so it has
        # to be mapped onto real colours before it can be shown.
        owner_plans = list(entry.get("owner_plans", []))
        opponent_plans = list(entry.get("opponent_plans", []))
        if report.owner == chess.BLACK:
            briefing.plans_black, briefing.plans_white = owner_plans, opponent_plans
        else:
            briefing.plans_white, briefing.plans_black = owner_plans, opponent_plans

        briefing.observations = self._observations(board, report)
        return briefing

    @staticmethod
    def _observations(board: chess.Board, report: StructureReport) -> List[str]:
        """Facts read straight off the board. Every line here is arithmetic."""
        notes: List[str] = []

        for color, facts, label in (
            (chess.WHITE, report.white, "White"),
            (chess.BLACK, report.black, "Black"),
        ):
            if facts.isolated:
                files = ", ".join(chess.FILE_NAMES[f] for f in facts.isolated)
                notes.append(f"{label} has an isolated pawn on the {files} file.")
            if facts.backward:
                files = ", ".join(chess.FILE_NAMES[f] for f in facts.backward)
                notes.append(
                    f"{label}'s {files}-pawn is backward: no friendly pawn can defend it."
                )
            if facts.doubled:
                files = ", ".join(chess.FILE_NAMES[f] for f in facts.doubled)
                notes.append(f"{label} has doubled pawns on the {files} file.")
            if facts.passed:
                squares = ", ".join(chess.square_name(s) for s in facts.passed)
                notes.append(f"{label} has a passed pawn on {squares}.")
            if facts.half_open_files:
                files = ", ".join(chess.FILE_NAMES[f] for f in facts.half_open_files)
                notes.append(f"{label} has a half-open {files} file for the rooks.")
            if report.bad_bishop.get(color):
                notes.append(
                    f"{label}'s bishop is hemmed in by its own centre pawns."
                )
            outposts = report.outposts.get(color, [])
            if outposts:
                squares = ", ".join(chess.square_name(s) for s in outposts[:3])
                notes.append(
                    f"{label} has an outpost on {squares}: no enemy pawn can attack it."
                )

        space = report.white.space - report.black.space
        if abs(space) >= 4:
            leader = "White" if space > 0 else "Black"
            notes.append(f"{leader} holds more space in the centre.")

        return notes

    # ---------------------------------------------------------- annotation

    def annotate(
        self,
        judgement: Judgement,
        board_before: chess.Board,
        move: chess.Move,
    ) -> Judgement:
        """Attach a plan-aware explanation to a graded move.

        The grade says how much the move cost. This says what the move did, and
        what the resulting position is about.
        """
        board_after = board_before.copy()
        if move in board_before.legal_moves:
            board_after.push(move)

        briefing = self.brief(board_after)
        judgement.plan = briefing

        book_move = self.book.lookup(board_after)
        judgement.is_book = book_move is not None
        if book_move is not None:
            judgement.opening = str(book_move)

        judgement.explanation = self._sentence(
            judgement, board_before, move, board_after, briefing
        )
        return judgement

    def _sentence(
        self,
        judgement: Judgement,
        board_before: chess.Board,
        move: chess.Move,
        board_after: chess.Board,
        briefing: PositionBriefing,
    ) -> str:
        parts: List[str] = []
        mover = board_before.turn

        if board_after.is_checkmate():
            return "Checkmate. The game ends here."

        if judgement.is_book and not judgement.grade.is_error:
            parts.append(f"Theory: {judgement.opening}.")
        else:
            parts.append(self._what_the_move_did(board_before, move, board_after))

        if judgement.grade.is_error and judgement.best_san:
            parts.append(
                f"{judgement.best_san} was stronger, worth "
                f"{judgement.win_loss:.0f}% more winning chances."
            )

        plans = briefing.plans_for(mover)
        if plans and not judgement.grade.is_error:
            parts.append(f"Plan: {plans[0]}")
        elif judgement.grade.is_error and briefing.typical_mistakes:
            parts.append(f"Watch out: {briefing.typical_mistakes[0]}")

        return " ".join(p for p in parts if p)

    @staticmethod
    def _what_the_move_did(
        board_before: chess.Board, move: chess.Move, board_after: chess.Board
    ) -> str:
        """Describe the move by its concrete effect on the position."""
        piece = board_before.piece_at(move.from_square)
        name = chess.piece_name(piece.piece_type).capitalize() if piece else "Piece"

        if board_before.is_castling(move):
            return "Castling: the king reaches safety and the rook joins the game."
        if board_after.is_check():
            return f"Check. The {name.lower()} forces a reply."
        if board_before.is_capture(move):
            captured = board_before.piece_at(move.to_square)
            what = chess.piece_name(captured.piece_type) if captured else "pawn"
            return f"Captures the {what} on {chess.square_name(move.to_square)}."
        if move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
            return f"The {name.lower()} takes central space on {chess.square_name(move.to_square)}."
        if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
            home = 0 if piece.color == chess.WHITE else 7
            if chess.square_rank(move.from_square) == home:
                return f"Develops the {name.lower()} into the game."
        return f"{name} to {chess.square_name(move.to_square)}."
