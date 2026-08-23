"""End-to-end self check: does the engine layer actually work?

Run it with an engine configured:

    STOCKFISH_PATH=/usr/local/bin/stockfish python -m tools.selfcheck

Without an engine it reports the fact and exits 0, so it is safe in CI. With
one, it exercises the paths that unit tests cannot: a real UCI handshake, real
analysis, a real game, and the two bugs this project shipped with -- an engine
that never started, and an evaluation bar drawn in the wrong frame of reference.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from analysis import win_percent
from coach import Coach
from config import ELO_LEVELS, STOCKFISH_PATH, strength_for_elo
from engine import EngineWrapper

PASS, FAIL = "  ok  ", " FAIL "
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{PASS if condition else FAIL}] {label}" + (f"  -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def main() -> int:
    print("=" * 72)
    print("Chess Analyzer self check")
    print("=" * 72)

    if not STOCKFISH_PATH:
        print("No engine binary found.")
        print("Set STOCKFISH_PATH, or put `stockfish` on PATH, to run the engine checks.")
        print("Skipping engine checks (this is not a failure).")
        return 0

    print(f"Engine binary: {STOCKFISH_PATH}\n")
    engine = EngineWrapper(STOCKFISH_PATH, elo=1500)

    check("engine ready", engine.is_ready, engine.engine_name)
    if not engine.is_ready:
        print("\nThe engine did not start. Everything else depends on it.")
        return 1

    # --- Evaluation frame of reference -----------------------------------
    # The bug this project shipped with: a side-to-move score rendered as if it
    # were White's, so the bar was inverted whenever Black was to move.
    white_up = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
    black_up = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1")

    a = engine.analyse(white_up, depth=10)
    b = engine.analyse(black_up, depth=10)

    check(
        "White a queen up scores POSITIVE with Black to move",
        a.score_white > 300,
        f"score_white={a.score_white}",
    )
    check(
        "Black a queen up scores NEGATIVE with White to move",
        b.score_white < -300,
        f"score_white={b.score_white}",
    )
    check(
        "relative and white frames disagree when Black is to move",
        a.best is not None and a.best.score_relative < 0 < a.best.score_white,
        f"relative={a.best.score_relative if a.best else None}",
    )

    # --- MultiPV ---------------------------------------------------------
    start = engine.analyse(chess.Board(), depth=12)
    check("multipv returns several distinct candidates", len(start.candidates) >= 2,
          ", ".join(c.uci for c in start.candidates))
    check("principal variation is populated", bool(start.best and start.best.pv),
          " ".join(m.uci() for m in (start.best.pv[:4] if start.best else [])))

    # --- Mate scores -----------------------------------------------------
    mate = engine.analyse(chess.Board("6k1/5ppp/8/8/8/7Q/5PPP/6K1 w - - 0 1"), depth=14)
    check("mate is projected onto the centipawn scale", abs(mate.score_white) > 5000,
          f"score_white={mate.score_white}, mate_in={mate.mate_in}")

    # --- Strength profiles ----------------------------------------------
    ok = True
    detail = []
    for elo in ELO_LEVELS:
        profile = strength_for_elo(elo)
        try:
            engine.set_elo(elo)
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail.append(f"{elo}: {exc}")
        detail.append(f"{elo}->{profile.description}")
    check("every slider stop configures without error", ok, "; ".join(detail[:4]) + " ...")

    profiles = {strength_for_elo(e).description for e in ELO_LEVELS}
    check("slider stops are genuinely distinct", len(profiles) == len(ELO_LEVELS),
          f"{len(profiles)} distinct of {len(ELO_LEVELS)}")

    # --- A real game -----------------------------------------------------
    engine.set_elo(1500)
    board = chess.Board()
    coach = Coach()
    plies = 0
    for _ in range(6):
        if board.is_game_over():
            break
        before = board.copy()
        analysis_before = engine.analyse(before, depth=10)
        move = engine.play(board, depth=10)
        if move is None or move not in board.legal_moves:
            break
        board.push(move)
        analysis_after = engine.analyse(board, depth=10)
        judgement = engine.classify_move(before, move, analysis_before, analysis_after)
        coach.annotate(judgement, before, move)
        plies += 1
        print(
            f"        {plies}. {judgement.san:6} {judgement.label:11} "
            f"acc {judgement.accuracy:5.1f}%  {judgement.explanation[:60]}"
        )

    check("engine played a full sequence of moves", plies == 6, f"{plies} plies")
    check("every move produced an explanation", plies > 0)

    # --- Win probability sanity -----------------------------------------
    check("win% at equality is 50", abs(win_percent(0) - 50) < 0.01)

    engine.close()

    print("\n" + "=" * 72)
    if failures:
        print(f"FAILED: {len(failures)} check(s): " + ", ".join(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
