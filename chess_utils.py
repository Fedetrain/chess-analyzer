# chess_utils.py
"""Small shared helpers: a memoised move generator and the analysis cache.

This module used to also carry two hand-written opening databases and a
template-based instructor. Both have been superseded and deleted rather than
left in place:

* opening recognition now lives in :mod:`openings`, backed by the full 3810-entry
  ECO corpus instead of 31 hand-written entries;
* the explanations now live in :mod:`coach`, which reasons about pawn structures
  instead of selecting a sentence from a fixed list.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

import chess

from config import LEGAL_MOVES_CACHE_SIZE


class ChessUtils:
    """Low-level board helpers."""

    @staticmethod
    @lru_cache(maxsize=LEGAL_MOVES_CACHE_SIZE)
    def get_legal_moves_cached(fen: str) -> Set[chess.Move]:
        """Legal moves for a FEN, memoised.

        The render loop asks for the legal moves of the selected piece on every
        frame; without memoisation that regenerates them 60 times a second for a
        position that has not changed.
        """
        return set(chess.Board(fen).legal_moves)

    @staticmethod
    def get_material_diff(board: chess.Board) -> int:
        """Material balance in pawns, from White's point of view."""
        values = {
            chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
            chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
        }
        score = 0
        for piece_type, value in values.items():
            score += value * len(board.pieces(piece_type, chess.WHITE))
            score -= value * len(board.pieces(piece_type, chess.BLACK))
        return score


class AnalysisCache:
    """An LRU cache with a TTL, keyed by position and depth.

    Undo and board flips revisit positions constantly, so caching turns a
    repeated engine search into a dict lookup. Entries expire because an
    analysis computed at one depth should not outlive the session that wanted it.
    """

    def __init__(self, max_size: int = 100, timeout_seconds: int = 30):
        self.max_size = max_size
        self.timeout = timeout_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._order: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        data, timestamp = self._cache[key]
        if time.time() - timestamp > self.timeout:
            self._remove(key)
            return None
        self._order.remove(key)
        self._order.append(key)
        return data

    def set(self, key: str, data: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self.max_size:
            self._remove_oldest()
        self._cache[key] = (data, time.time())
        self._order.append(key)

    def _remove(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
            self._order.remove(key)

    def _remove_oldest(self) -> None:
        if self._order:
            self._remove(self._order[0])
