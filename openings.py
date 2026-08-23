# openings.py
"""Opening identification against the full ECO corpus.

The previous implementation matched against 15 hand-written UCI sequences and
16 hand-written FEN strings, so anything outside about thirty positions was
reported as "uncommon opening". This module loads the 3810-entry CC0 data set
from ``data/eco`` instead (see ``data/eco/SOURCE.md``).

Two lookups, in this order:

1. **Exact position key.** Every opening in the corpus is indexed by the
   position its line reaches, using an EPD-style key that drops the halfmove and
   fullmove counters. Dropping the counters is what makes the lookup
   transposition-aware: the Najdorf reached by a different move order is the
   same key.
2. **Longest played prefix.** Walking the game's own move stack backwards finds
   the most specific opening the game has passed through, so a game that has
   left book still reports the last opening it was actually in.

Both run off one dict built once at import, so identification is a hash lookup
per frame rather than a scan over the corpus.
"""

from __future__ import annotations

import csv
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

import chess

log = logging.getLogger(__name__)

ECO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "eco")


@dataclass(frozen=True)
class Opening:
    """One ECO entry."""

    eco: str
    name: str
    pgn: str
    epd: str
    ply: int

    @property
    def family(self) -> str:
        """The opening family, i.e. the part before the first colon.

        "Sicilian Defense: Najdorf Variation, English Attack" -> "Sicilian Defense".
        Used to group a repertoire and to key the plan knowledge base.
        """
        return self.name.split(":")[0].strip()

    @property
    def variation(self) -> str:
        parts = self.name.split(":", 1)
        return parts[1].strip() if len(parts) > 1 else ""

    def __str__(self) -> str:
        return f"{self.eco} {self.name}"


def position_key(board: chess.Board) -> str:
    """A transposition-tolerant position key.

    The first four FEN fields only: piece placement, side to move, castling
    rights and the en-passant square. The halfmove clock and fullmove number are
    deliberately dropped -- they describe *how* the position was reached, not
    the position, and keeping them would defeat transposition matching.
    """
    return " ".join(board.fen().split(" ")[:4])


def _parse_pgn_moves(pgn: str) -> list[chess.Move]:
    """Turn an ECO ``pgn`` column ("1. e4 c5 2. Nf3") into a move list."""
    board = chess.Board()
    moves: list[chess.Move] = []
    for token in pgn.split():
        if token[0].isdigit() and ("." in token):
            continue
        token = token.strip()
        if not token or token in ("1-0", "0-1", "1/2-1/2", "*"):
            continue
        try:
            move = board.parse_san(token)
        except ValueError:
            return []
        moves.append(move)
        board.push(move)
    return moves


def _iter_rows(directory: str) -> Iterator[tuple[str, str, str]]:
    for letter in "abcde":
        path = os.path.join(directory, f"{letter}.tsv")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header = next(reader, None)
            if header and header[0].strip().lower() != "eco":
                yield tuple(header[:3])  # type: ignore[misc]
            for row in reader:
                if len(row) >= 3:
                    yield row[0].strip(), row[1].strip(), row[2].strip()


class OpeningBook:
    """The ECO corpus, indexed by position."""

    def __init__(self, directory: str = ECO_DIR):
        self.by_epd: dict[str, Opening] = {}
        self._load(directory)

    def _load(self, directory: str) -> None:
        for eco, name, pgn in _iter_rows(directory):
            moves = _parse_pgn_moves(pgn)
            if not moves:
                continue
            board = chess.Board()
            for move in moves:
                board.push(move)
            key = position_key(board)
            existing = self.by_epd.get(key)
            # Prefer the more specific name when two entries share a position.
            if existing is None or len(name) > len(existing.name):
                self.by_epd[key] = Opening(
                    eco=eco, name=name, pgn=pgn, epd=key, ply=len(moves)
                )
        if not self.by_epd:
            log.warning("No ECO data found in %s - opening names unavailable.", directory)

    def __len__(self) -> int:
        return len(self.by_epd)

    # ------------------------------------------------------------- lookups

    def lookup(self, board: chess.Board) -> Opening | None:
        """Exact match for the position currently on *board*."""
        return self.by_epd.get(position_key(board))

    def identify(self, board: chess.Board) -> Opening | None:
        """The most specific opening this game has reached.

        Walks the move stack backwards, so a game that has already left book
        still reports the last opening it genuinely passed through.
        """
        if exact := self.lookup(board):
            return exact

        replay = board.copy()
        while replay.move_stack:
            replay.pop()
            if found := self.lookup(replay):
                return found
        return None

    def describe(self, board: chess.Board) -> str:
        """A display string for the analysis panel."""
        if not board.move_stack:
            return "Starting position"
        opening = self.identify(board)
        if opening is None:
            return "Out of book"
        return str(opening)

    def continuations(self, board: chess.Board) -> list[tuple[chess.Move, Opening]]:
        """Book moves from this position that lead to a named opening.

        This is what lets the trainer offer real theory moves without a network
        call, and what gives the repertoire builder its suggestions.
        """
        found: list[tuple[chess.Move, Opening]] = []
        for move in board.legal_moves:
            board.push(move)
            opening = self.lookup(board)
            board.pop()
            if opening is not None:
                found.append((move, opening))
        return found

    def search(self, text: str, limit: int = 25) -> list[Opening]:
        """Case-insensitive substring search over opening names."""
        needle = text.strip().lower()
        if not needle:
            return []
        hits = [o for o in self.by_epd.values() if needle in o.name.lower()]
        hits.sort(key=lambda o: (len(o.name), o.name))
        return hits[:limit]

    def family_line(self, family: str) -> list[Opening]:
        """Every entry belonging to one opening family."""
        return sorted(
            (o for o in self.by_epd.values() if o.family.lower() == family.lower()),
            key=lambda o: o.ply,
        )


@lru_cache(maxsize=1)
def get_book() -> OpeningBook:
    """The shared, lazily-built opening book."""
    return OpeningBook()
