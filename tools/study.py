"""Command line for the opening study system.

    python -m tools.study build   --color white --line "e4 e5 Nf3 Nc6 Bb5" --name Ruy
    python -m tools.study import  --color white --pgn my_repertoire.pgn
    python -m tools.study explain --line "d4 d5 c4 e6 Nc3 Nf6 cxd5 exd5"
    python -m tools.study drill   --color white [--rounds 10]
    python -m tools.study review  --pgn game.pgn --color white
    python -m tools.study stats   --color white

Everything except ``review`` works with no engine and no network.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from coach import Coach
from config import DATA_DIR, STOCKFISH_PATH
from openings import get_book
from repertoire import Repertoire
from review import Reviewer, suggest_study
from trainer import Answer, DrillMode, StudySession

RULE = "-" * 72


def _paths(color: str):
    side = "white" if color.lower().startswith("w") else "black"
    return (
        os.path.join(DATA_DIR, f"repertoire_{side}.json"),
        os.path.join(DATA_DIR, f"study_{side}.json"),
        chess.WHITE if side == "white" else chess.BLACK,
    )


def _load_repertoire(color: str) -> tuple[Repertoire, str, str]:
    rep_path, study_path, side = _paths(color)
    if os.path.exists(rep_path):
        return Repertoire.load(rep_path), rep_path, study_path
    return Repertoire(name=f"{color.title()} repertoire", color=side), rep_path, study_path


def cmd_build(args) -> int:
    rep, rep_path, _ = _load_repertoire(args.color)
    added = rep.add_san_line(*args.line.split(), comment=args.comment or "")
    if args.name:
        rep.name = args.name
    rep.save(rep_path)
    print(f"Added {added} new edges. Repertoire now: {rep.coverage()}")
    print(f"Saved to {rep_path}")
    return 0


def cmd_import(args) -> int:
    rep, rep_path, _ = _load_repertoire(args.color)
    if not os.path.exists(args.pgn):
        print(f"No such file: {args.pgn}")
        return 1
    added = rep.import_pgn(args.pgn)
    rep.save(rep_path)
    print(f"Imported {args.pgn}: {added} new edges.")
    print(f"Repertoire: {rep.coverage()}")
    return 0


def cmd_explain(args) -> int:
    board = chess.Board()
    for san in args.line.split():
        try:
            board.push_san(san)
        except ValueError:
            print(f"Illegal move: {san}")
            return 1

    briefing = Coach().brief(board)
    print(RULE)
    print(f"Position after: {args.line}")
    print(RULE)
    print(f"Opening   : {briefing.opening or 'not in book'}")
    print(f"Structure : {briefing.structure_name}")
    if briefing.summary:
        print(f"\n{briefing.summary}")

    for label, plans in (("White", briefing.plans_white), ("Black", briefing.plans_black)):
        if plans:
            print(f"\nPlans for {label}:")
            for plan in plans:
                print(f"  - {plan}")

    if briefing.observations:
        print("\nFrom the position itself:")
        for note in briefing.observations:
            print(f"  * {note}")

    for label, items in (
        ("Strong pieces", briefing.good_pieces),
        ("Weak pieces", briefing.bad_pieces),
        ("Typical mistakes", briefing.typical_mistakes),
        ("Traps", briefing.traps),
    ):
        if items:
            print(f"\n{label}:")
            for item in items:
                print(f"  - {item}")

    print(f"\nFurther reading: {briefing.study_url}")
    return 0


def cmd_drill(args) -> int:
    rep, _, study_path = _load_repertoire(args.color)
    if not rep.own_moves:
        print("Repertoire is empty. Add lines with `build` or `import` first.")
        return 1

    session = StudySession(rep, path=study_path)
    mode = DrillMode.WHOLE_LINE if args.mode == "line" else DrillMode.SINGLE_POSITION
    print(f"Scheduler: {session.scheduler_name}")
    print(f"{len(session.due_cards())} card(s) due.\n")

    correct = 0
    asked = 0
    for _ in range(args.rounds):
        question = session.next_question(mode=mode)
        if question is None:
            print("Nothing more is due. Well done.")
            break

        asked += 1
        print(RULE)
        print(question.board.unicode(invert_color=True, empty_square="."))
        side = "White" if question.board.turn == chess.WHITE else "Black"
        print(f"\n{side} to play. Your move? (or 'q' to stop, '?' to give up)")

        try:
            # Strip a leading BOM: some shells prepend one to piped input, and
            # it would otherwise make a perfectly good move unparseable.
            reply = input("> ").lstrip("﻿").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if reply.lower() in ("q", "quit", "exit"):
            break

        if reply == "?":
            session.record(question.card_id, Answer.AGAIN)
            print(f"The move is {question.expected.san}.")
            continue

        try:
            played = question.board.parse_san(reply)
        except ValueError:
            print("Not a legal move here.")
            session.record(question.card_id, Answer.AGAIN)
            continue

        ok, _ = session.answer(question, played)
        if ok:
            correct += 1
            print(f"Correct: {question.expected.san}.")
        else:
            print(f"No. The repertoire move is {question.expected.san}.")
            if question.expected.comment:
                print(f"  {question.expected.comment}")

        after = question.board.copy()
        after.push(question.expected.move)
        briefing = Coach(book=get_book()).brief(after)
        if briefing.plans_for(question.board.turn):
            print(f"  Idea: {briefing.plans_for(question.board.turn)[0]}")

    if asked:
        print(f"\n{correct}/{asked} correct.")
    print(f"Progress: {session.progress()}")
    return 0


def cmd_review(args) -> int:
    rep = None
    if not args.no_repertoire:
        rep, _, _ = _load_repertoire(args.color)
        if not len(rep):
            rep = None

    engine = None
    if STOCKFISH_PATH:
        from engine import EngineWrapper

        engine = EngineWrapper(STOCKFISH_PATH)
    else:
        print("No engine configured: reporting opening and repertoire only.\n")

    reviewer = Reviewer(engine=engine, depth=args.depth)
    color = chess.WHITE if args.color.lower().startswith("w") else chess.BLACK

    try:
        reviews = reviewer.review_pgn(args.pgn, color=color, rep=rep)
    finally:
        if engine is not None:
            engine.close()

    if not reviews:
        print(f"No games found in {args.pgn}")
        return 1

    for index, review in enumerate(reviews, start=1):
        print(RULE)
        print(f"Game {index}")
        print(RULE)
        print(review.summary())
        print("\nWhat to study:")
        for line in suggest_study(review):
            print(f"  - {line}")
        print()
    return 0


def cmd_stats(args) -> int:
    rep, rep_path, study_path = _load_repertoire(args.color)
    if not os.path.exists(rep_path):
        print("No repertoire yet. Create one with `build` or `import`.")
        return 1

    session = StudySession(rep, path=study_path)
    print(RULE)
    print(f"Repertoire: {rep.name}")
    print(RULE)
    for key, value in rep.coverage().items():
        print(f"  {key:16}: {value}")
    print()
    for key, value in session.progress().items():
        label = f"{value:.1%}" if key == "accuracy" else value
        print(f"  {key:16}: {label}")

    weakest = session.weakest()
    if weakest:
        print("\nWeakest positions:")
        for entry, stats in weakest:
            print(f"  {entry.san:8} missed {stats.lapses}x in {stats.reviews} reviews")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.study", description="Opening repertoire trainer."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def with_color(p):
        p.add_argument("--color", default="white", choices=["white", "black"])
        return p

    p = with_color(sub.add_parser("build", help="add a line to the repertoire"))
    p.add_argument("--line", required=True, help='SAN moves, e.g. "e4 e5 Nf3"')
    p.add_argument("--name")
    p.add_argument("--comment")
    p.set_defaults(func=cmd_build)

    p = with_color(sub.add_parser("import", help="import a PGN repertoire"))
    p.add_argument("--pgn", required=True)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("explain", help="explain the plans in a position")
    p.add_argument("--line", required=True)
    p.set_defaults(func=cmd_explain)

    p = with_color(sub.add_parser("drill", help="drill due positions"))
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--mode", default="line", choices=["line", "spot"])
    p.set_defaults(func=cmd_drill)

    p = with_color(sub.add_parser("review", help="review a saved game"))
    p.add_argument("--pgn", required=True)
    p.add_argument("--depth", type=int, default=12)
    p.add_argument("--no-repertoire", action="store_true")
    p.set_defaults(func=cmd_review)

    p = with_color(sub.add_parser("stats", help="show study progress"))
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
