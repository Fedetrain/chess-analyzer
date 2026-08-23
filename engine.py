# engine.py
"""Stockfish (or any UCI engine) driven through python-chess's own engine layer.

Why ``chess.engine`` and not the ``stockfish`` PyPI wrapper
-----------------------------------------------------------
The wrapper was the project's single most damaging dependency: it is a
synchronous shim whose default option table still sends Stockfish four options
the engine deleted years ago, and whose ``UCI_LimitStrength`` value type changed
from ``str`` to ``bool`` in a later release -- which silently killed engine
startup here. ``chess.engine`` ships with python-chess, which this project
already depends on, so dropping the wrapper *removes* a dependency.

It also removes a whole class of bugs by construction:

* ``analyse()`` returns a :class:`chess.engine.PovScore`. ``.white()`` and
  ``.relative()`` are separate, explicit methods, so an evaluation can no longer
  be rendered in the wrong frame of reference by accident.
* ``Score.score(mate_score=N)`` projects mates onto the centipawn scale natively;
  no hand-rolled normalisation.
* ``multipv=`` returns genuinely independent principal variations.
* ``SimpleEngine`` is documented thread-safe and serialises commands internally.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import chess
import chess.engine

from analysis import Judgement, classify
from chess_utils import AnalysisCache
from config import (
    DEPTH_FAST_ANALYSIS,
    DEPTH_FULL_ANALYSIS,
    ENGINE_HASH_MB,
    ENGINE_THREADS,
    MATE_SCORE,
    MULTIPV,
    STOCKFISH_MISSING_MESSAGE,
    strength_for_elo,
)

log = logging.getLogger(__name__)


@dataclass
class MoveCandidate:
    """One principal variation returned by the engine."""

    move: chess.Move
    score_white: int          # centipawns, White's point of view, mates projected
    score_relative: int       # centipawns, side-to-move's point of view
    pv: list[chess.Move] = field(default_factory=list)
    mate_in: int | None = None

    @property
    def uci(self) -> str:
        return self.move.uci()


@dataclass
class Analysis:
    """The engine's verdict on one position.

    ``fen`` is carried so a caller can tell whether a result that arrived from a
    worker thread still describes the position on the board.
    """

    fen: str
    depth: int
    candidates: list[MoveCandidate] = field(default_factory=list)
    score_white: int = 0
    mate_in: int | None = None

    @property
    def best(self) -> MoveCandidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def is_empty(self) -> bool:
        return not self.candidates


EMPTY_ANALYSIS = Analysis(fen="", depth=0)


def _to_cp(score: chess.engine.Score) -> int:
    """Project a score (centipawns or mate) onto a single centipawn scale."""
    return int(score.score(mate_score=MATE_SCORE))


class EngineWrapper:
    """Owns the UCI session and turns raw engine output into domain objects.

    Thread-safety: ``SimpleEngine`` already serialises its own commands, but the
    strength configuration is mutable shared state, so reconfiguration is guarded
    by ``self._lock`` to keep a slider drag from interleaving with a search.
    """

    def __init__(self, path: str | None, elo: int = 1500):
        self._lock = threading.RLock()
        self._engine: chess.engine.SimpleEngine | None = None
        self.analysis_cache = AnalysisCache(max_size=200, timeout_seconds=60)
        self.engine_name = "none"
        self.current_elo = elo

        if not path:
            log.warning("No engine binary configured.\n%s", STOCKFISH_MISSING_MESSAGE)
            return

        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(path, timeout=15.0)
            self.engine_name = self._engine.id.get("name", "unknown UCI engine")
            self._configure_base()
            self.set_elo(elo)
            log.info("Engine ready: %s (%s)", self.engine_name, path)
        except Exception as exc:  # noqa: BLE001 - a broken engine must never crash the GUI
            log.error("Engine initialisation failed: %s", exc)
            log.info("%s", STOCKFISH_MISSING_MESSAGE)
            self._close_quietly()

    # ------------------------------------------------------------------ setup

    def _supported(self, name: str) -> bool:
        return self._engine is not None and name in self._engine.options

    def _configure_base(self) -> None:
        """Apply only options the engine actually advertises.

        Sending an unknown option is exactly how the previous implementation
        broke, so every key is checked against the engine's own option table
        before being sent.
        """
        # MultiPV is deliberately absent: python-chess manages it itself and
        # rejects an explicit configure() ("cannot set MultiPV which is
        # automatically managed"). It is passed per-call to analyse() instead.
        wanted = {"Threads": ENGINE_THREADS, "Hash": ENGINE_HASH_MB}
        opts = {k: v for k, v in wanted.items() if self._supported(k)}
        if opts:
            self._engine.configure(opts)

    def set_elo(self, elo: int) -> None:
        """Configure playing strength for a requested Elo.

        Stockfish's ``UCI_Elo`` bottoms out at 1320, so anything below that is
        expressed with ``Skill Level`` plus a node ceiling instead. The mapping
        lives in :func:`config.strength_for_elo`.
        """
        if not self._engine:
            self.current_elo = elo
            return

        profile = strength_for_elo(elo)
        opts: dict[str, Any] = {}

        if profile.use_uci_elo and self._supported("UCI_Elo"):
            opts["UCI_LimitStrength"] = True
            opts["UCI_Elo"] = self._clamp_option("UCI_Elo", profile.uci_elo)
        else:
            if self._supported("UCI_LimitStrength"):
                opts["UCI_LimitStrength"] = False
            if self._supported("Skill Level"):
                opts["Skill Level"] = self._clamp_option("Skill Level", profile.skill_level)

        with self._lock:
            try:
                if opts:
                    self._engine.configure(opts)
                self.current_elo = elo
                self._node_limit = profile.node_limit
            except Exception as exc:  # noqa: BLE001
                log.error("Could not apply strength %s: %s", elo, exc)

    def _clamp_option(self, name: str, value: int) -> int:
        opt = self._engine.options[name]
        if opt.min is not None:
            value = max(opt.min, value)
        if opt.max is not None:
            value = min(opt.max, value)
        return value

    @property
    def is_ready(self) -> bool:
        return self._engine is not None

    def close(self) -> None:
        self._close_quietly()

    def _close_quietly(self) -> None:
        engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.quit()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> EngineWrapper:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --------------------------------------------------------------- analysis

    def analyse(self, board: chess.Board, depth: int = DEPTH_FAST_ANALYSIS) -> Analysis:
        """Analyse *board*, with an LRU cache keyed by position and depth."""
        if not self._engine:
            return EMPTY_ANALYSIS

        fen = board.fen()
        key = f"{fen}_{depth}"
        if (cached := self.analysis_cache.get(key)) is not None:
            return cached

        try:
            with self._lock:
                infos = self._engine.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    multipv=MULTIPV,
                )
        except Exception as exc:  # noqa: BLE001
            log.error("Analysis failed: %s", exc)
            return EMPTY_ANALYSIS

        if isinstance(infos, dict):        # multipv=None collapses to a single dict
            infos = [infos]

        candidates: list[MoveCandidate] = []
        for info in infos:
            pv = info.get("pv") or []
            score = info.get("score")
            if not pv or score is None:
                continue
            candidates.append(
                MoveCandidate(
                    move=pv[0],
                    score_white=_to_cp(score.white()),
                    score_relative=_to_cp(score.relative),
                    pv=list(pv[:8]),
                    mate_in=score.white().mate(),
                )
            )

        result = Analysis(
            fen=fen,
            depth=depth,
            candidates=candidates,
            score_white=candidates[0].score_white if candidates else 0,
            mate_in=candidates[0].mate_in if candidates else None,
        )
        self.analysis_cache.set(key, result)
        return result

    def analyse_fen(self, fen: str, depth: int = DEPTH_FAST_ANALYSIS) -> Analysis:
        return self.analyse(chess.Board(fen), depth)

    def deep_analyse(self, board: chess.Board) -> Analysis:
        return self.analyse(board, depth=DEPTH_FULL_ANALYSIS)

    # ------------------------------------------------------------------- play

    def play(self, board: chess.Board, depth: int = DEPTH_FAST_ANALYSIS) -> chess.Move | None:
        """Ask the engine for a move at the configured strength."""
        if not self._engine:
            return None

        node_limit = getattr(self, "_node_limit", None)
        limit = (
            chess.engine.Limit(nodes=node_limit)
            if node_limit
            else chess.engine.Limit(depth=depth)
        )
        try:
            with self._lock:
                result = self._engine.play(board, limit)
            return result.move
        except Exception as exc:  # noqa: BLE001
            log.error("Engine move failed: %s", exc)
            return None

    # --------------------------------------------------------------- grading

    def classify_move(
        self,
        board_before: chess.Board,
        move: chess.Move,
        analysis_before: Analysis,
        analysis_after: Analysis,
    ) -> Judgement:
        """Grade *move* using win-probability loss (see :mod:`analysis`)."""
        return classify(board_before, move, analysis_before, analysis_after)
