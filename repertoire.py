# repertoire.py
"""An opening repertoire stored as a graph of positions.

Why a graph and not a tree
--------------------------
Most trainers store a repertoire as a tree of *lines*, which means the same
position reached by two move orders becomes two unrelated nodes: you drill it
twice, and mastering one teaches the scheduler nothing about the other. Storing
**edges keyed by position** (``position_key -> move``) instead makes
transpositions collapse for free, makes importing the same PGN twice a no-op,
and gives the spaced-repetition system a natural, stable card identity.

Only *your own* moves become cards. The opponent's replies are the prompt: they
are sampled from the graph to pose the question, never asked of you.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass

import chess
import chess.pgn

from openings import position_key

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class RepertoireMove:
    """One edge: from a position, this move.

    ``own`` marks the moves the student is expected to produce. Those are the
    only ones that become study cards.
    """

    epd: str
    uci: str
    san: str
    own: bool
    comment: str = ""
    weight: int = 1          # how often this branch was seen on import

    @property
    def move(self) -> chess.Move:
        return chess.Move.from_uci(self.uci)

    @property
    def card_id(self) -> str:
        """Stable identity of the study card, independent of move order."""
        return f"{self.epd}|{self.uci}"

    def to_dict(self) -> dict:
        return {
            "epd": self.epd,
            "uci": self.uci,
            "san": self.san,
            "own": self.own,
            "comment": self.comment,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RepertoireMove:
        return cls(
            epd=data["epd"],
            uci=data["uci"],
            san=data.get("san", ""),
            own=bool(data.get("own", False)),
            comment=data.get("comment", ""),
            weight=int(data.get("weight", 1)),
        )


class Repertoire:
    """One colour's repertoire: a set of position -> move edges."""

    def __init__(self, name: str = "Repertoire", color: chess.Color = chess.WHITE):
        self.name = name
        self.color = color
        #: position key -> {uci: RepertoireMove}
        self.edges: dict[str, dict[str, RepertoireMove]] = {}

    # ------------------------------------------------------------- basics

    def __len__(self) -> int:
        return sum(len(m) for m in self.edges.values())

    @property
    def own_moves(self) -> list[RepertoireMove]:
        """Every move the student is expected to know: the study cards."""
        return [m for moves in self.edges.values() for m in moves.values() if m.own]

    @property
    def position_count(self) -> int:
        return len(self.edges)

    def add(self, board: chess.Board, move: chess.Move, comment: str = "") -> RepertoireMove:
        """Record one edge. Adding the same edge twice only bumps its weight."""
        key = position_key(board)
        own = board.turn == self.color
        san = board.san(move)

        bucket = self.edges.setdefault(key, {})
        existing = bucket.get(move.uci())
        if existing is not None:
            existing.weight += 1
            if comment and not existing.comment:
                existing.comment = comment
            return existing

        entry = RepertoireMove(
            epd=key, uci=move.uci(), san=san, own=own, comment=comment
        )
        bucket[move.uci()] = entry
        return entry

    def moves_from(self, board: chess.Board) -> list[RepertoireMove]:
        return list(self.edges.get(position_key(board), {}).values())

    def own_move_from(self, board: chess.Board) -> RepertoireMove | None:
        """The move the student is supposed to play here, if any."""
        for entry in self.moves_from(board):
            if entry.own:
                return entry
        return None

    def opponent_moves_from(self, board: chess.Board) -> list[RepertoireMove]:
        return [e for e in self.moves_from(board) if not e.own]

    def knows(self, board: chess.Board) -> bool:
        return position_key(board) in self.edges

    # -------------------------------------------------------------- import

    def add_line(self, moves: Iterable[chess.Move], comment: str = "") -> int:
        """Add a full line from the starting position. Returns edges added."""
        board = chess.Board()
        added = 0
        for move in moves:
            if move not in board.legal_moves:
                log.warning("Illegal move %s in line, stopping.", move)
                break
            before = len(self)
            self.add(board, move, comment=comment)
            added += len(self) - before
            board.push(move)
        return added

    def add_san_line(self, *sans: str, comment: str = "") -> int:
        board = chess.Board()
        moves: list[chess.Move] = []
        for san in sans:
            move = board.parse_san(san)
            moves.append(move)
            board.push(move)
        return self.add_line(moves, comment=comment)

    def import_pgn_game(self, game: chess.pgn.Game, include_variations: bool = True) -> int:
        """Import one PGN game, following variations as alternative branches."""
        added = 0

        def walk(node: chess.pgn.GameNode) -> None:
            nonlocal added
            board = node.board()
            children = node.variations if include_variations else node.variations[:1]
            for child in children:
                before = len(self)
                self.add(board, child.move, comment=(child.comment or "").strip())
                added += len(self) - before
                walk(child)

        walk(game)
        return added

    def import_pgn(self, path: str, include_variations: bool = True) -> int:
        """Import every game in a PGN file. Re-importing is idempotent."""
        added = 0
        with open(path, encoding="utf-8", errors="replace") as handle:
            while (game := chess.pgn.read_game(handle)) is not None:
                added += self.import_pgn_game(game, include_variations)
        return added

    # ------------------------------------------------------------ traversal

    def lines(self, max_depth: int = 40) -> list[list[RepertoireMove]]:
        """Enumerate the repertoire as complete lines, for display.

        Depth-limited and cycle-guarded: a position graph can contain loops that
        a tree cannot, so a naive walk would not terminate.
        """
        found: list[list[RepertoireMove]] = []

        def walk(board: chess.Board, path: list[RepertoireMove], seen: set[str]) -> None:
            if len(path) >= max_depth:
                found.append(list(path))
                return
            options = self.moves_from(board)
            if not options:
                if path:
                    found.append(list(path))
                return
            for entry in options:
                key = entry.card_id
                if key in seen:
                    continue
                board.push(entry.move)
                path.append(entry)
                walk(board, path, seen | {key})
                path.pop()
                board.pop()

        walk(chess.Board(), [], set())
        return found

    def find_deviation(
        self, moves: Iterable[chess.Move]
    ) -> tuple[int, chess.Move, RepertoireMove] | None:
        """Where a game left the repertoire.

        Returns ``(ply, move_played, expected_move)`` for the first of the
        student's own moves that departs from the book, or ``None`` if the game
        never deviated. Only the student's moves count: an opponent playing
        something unprepared is a gap in the repertoire, not a mistake.
        """
        board = chess.Board()
        for ply, move in enumerate(moves):
            if board.turn == self.color:
                expected = self.own_move_from(board)
                if expected is not None and expected.uci != move.uci():
                    return ply, move, expected
            if move not in board.legal_moves:
                break
            board.push(move)
        return None

    def coverage(self) -> dict[str, int]:
        own = self.own_moves
        return {
            "positions": self.position_count,
            "edges": len(self),
            "own_moves": len(own),
            "opponent_moves": len(self) - len(own),
        }

    # ----------------------------------------------------------- persistence

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "color": "white" if self.color == chess.WHITE else "black",
            "edges": [m.to_dict() for bucket in self.edges.values() for m in bucket.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Repertoire:
        rep = cls(
            name=data.get("name", "Repertoire"),
            color=chess.WHITE if data.get("color", "white") == "white" else chess.BLACK,
        )
        for raw in data.get("edges", []):
            entry = RepertoireMove.from_dict(raw)
            rep.edges.setdefault(entry.epd, {})[entry.uci] = entry
        return rep

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        os.replace(tmp, path)      # atomic: a crash mid-write cannot corrupt it

    @classmethod
    def load(cls, path: str) -> Repertoire:
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))
