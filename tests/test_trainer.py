"""Spaced-repetition drilling: FSRS scheduling, wrong answers, persistence."""

import random
from datetime import datetime, timedelta, timezone

import chess
import pytest

from repertoire import Repertoire
from trainer import (
    FSRS_AVAILABLE,
    Answer,
    DrillMode,
    StudySession,
    _Sm2Scheduler,
    make_scheduler,
)


def ruy() -> Repertoire:
    rep = Repertoire(name="Ruy", color=chess.WHITE)
    rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4")
    return rep


@pytest.fixture
def session(tmp_path) -> StudySession:
    return StudySession(ruy(), path=str(tmp_path / "study.json"), rng=random.Random(7))


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


class TestSchedulerSelection:
    def test_fsrs_is_available_and_preferred(self):
        """The roadmap chose FSRS-6; confirm it is actually what runs."""
        assert FSRS_AVAILABLE, "fsrs should be installed - see requirements"
        assert make_scheduler().name == "FSRS-6"

    def test_fallback_exists_when_fsrs_is_missing(self):
        """The trainer must still work without the optional dependency."""
        rep = ruy()
        s = StudySession(rep, scheduler=_Sm2Scheduler())
        assert s.scheduler_name.startswith("SM-2")
        assert s.due_cards(NOW)


class TestDrilling:
    def test_all_cards_start_due(self, session):
        assert len(session.due_cards(NOW)) == len(session.repertoire.own_moves)

    def test_only_own_moves_are_cards(self, session):
        assert {m.san for m in session.repertoire.own_moves} == {"e4", "Nf3", "Bb5", "Ba4"}

    def test_next_question_is_answerable(self, session):
        q = session.next_question(now=NOW)
        assert q is not None
        assert q.expected.move in q.board.legal_moves

    def test_route_reaches_the_card_position(self, session):
        from openings import position_key

        q = session.next_question(mode=DrillMode.WHOLE_LINE, now=NOW)
        assert position_key(q.board) == q.expected.epd

    def test_correct_answer_accepted(self, session):
        q = session.next_question(now=NOW)
        correct, _ = session.answer(q, q.expected.move, now=NOW)
        assert correct

    def test_wrong_answer_rejected(self, session):
        q = session.next_question(now=NOW)
        wrong = next(m for m in q.board.legal_moves if m.uci() != q.expected.uci)
        correct, _ = session.answer(q, wrong, now=NOW)
        assert not correct

    def test_opponent_reply_comes_from_the_repertoire(self, session):
        board = chess.Board()
        board.push_san("e4")
        reply = session.opponent_reply(board)
        assert reply is not None
        assert board.san(reply) == "e5"

    def test_opponent_reply_none_outside_book(self, session):
        board = chess.Board()
        board.push_san("d4")
        assert session.opponent_reply(board) is None


class TestSpacedRepetition:
    def test_wrong_answers_come_back_sooner_than_right_ones(self, session):
        """The core promise of the feature."""
        cards = session.repertoire.own_moves
        failed, passed = cards[0], cards[1]

        session.record(failed.card_id, Answer.AGAIN, NOW)
        session.record(passed.card_id, Answer.GOOD, NOW)

        assert session.due_in(failed.card_id, NOW) < session.due_in(passed.card_id, NOW)

    def test_easy_is_scheduled_further_out_than_good(self, session):
        cards = session.repertoire.own_moves
        session.record(cards[0].card_id, Answer.GOOD, NOW)
        session.record(cards[1].card_id, Answer.EASY, NOW)
        assert session.due_in(cards[1].card_id, NOW) > session.due_in(cards[0].card_id, NOW)

    def test_repeated_success_lengthens_the_interval(self, session):
        card = session.repertoire.own_moves[0]
        when = NOW
        intervals = []
        for _ in range(4):
            session.record(card.card_id, Answer.GOOD, when)
            gap = session.due_in(card.card_id, when)
            intervals.append(gap)
            when = when + gap + timedelta(seconds=1)
        assert intervals[-1] > intervals[0]

    def test_a_failed_card_is_prioritised(self, session):
        cards = session.repertoire.own_moves
        for card in cards:
            session.record(card.card_id, Answer.GOOD, NOW)
        session.record(cards[2].card_id, Answer.AGAIN, NOW)

        later = NOW + timedelta(minutes=5)
        due = session.due_cards(later)
        assert due and due[0].card_id == cards[2].card_id


class TestPersistence:
    def test_state_survives_reload(self, tmp_path):
        """The roadmap's acceptance criterion: progress must not be lost."""
        path = str(tmp_path / "study.json")
        rep = ruy()

        first = StudySession(rep, path=path)
        card = first.repertoire.own_moves[0]
        first.record(card.card_id, Answer.AGAIN, NOW)
        remembered = first.due_in(card.card_id, NOW)

        second = StudySession(ruy(), path=path)
        assert card.card_id in second.states
        assert second.due_in(card.card_id, NOW) == remembered

    def test_stats_survive_reload(self, tmp_path):
        path = str(tmp_path / "study.json")
        first = StudySession(ruy(), path=path)
        card = first.repertoire.own_moves[0]
        first.record(card.card_id, Answer.AGAIN, NOW)

        second = StudySession(ruy(), path=path)
        assert second.stats[card.card_id].lapses == 1

    def test_corrupt_state_file_degrades_quietly(self, tmp_path):
        path = tmp_path / "study.json"
        path.write_text("{ not json", encoding="utf-8")
        s = StudySession(ruy(), path=str(path))
        assert s.due_cards(NOW)          # still usable


class TestReports:
    def test_progress_counts(self, session):
        card = session.repertoire.own_moves[0]
        session.record(card.card_id, Answer.GOOD, NOW)
        report = session.progress()
        assert report["total_cards"] == 4
        assert report["studied"] == 1
        assert report["scheduler"] == session.scheduler_name

    def test_weakest_surfaces_lapsed_cards(self, session):
        cards = session.repertoire.own_moves
        session.record(cards[1].card_id, Answer.AGAIN, NOW)
        session.record(cards[1].card_id, Answer.AGAIN, NOW)
        session.record(cards[0].card_id, Answer.GOOD, NOW)

        weakest = session.weakest()
        assert weakest
        assert weakest[0][0].card_id == cards[1].card_id
        assert weakest[0][1].lapses == 2
