"""Game review: deviation detection and engine-free degradation."""

import io

import chess
import chess.pgn
import pytest

from repertoire import Repertoire
from review import Reviewer, suggest_study


def moves_from_san(*sans):
    board = chess.Board()
    out = []
    for san in sans:
        move = board.parse_san(san)
        out.append(move)
        board.push(move)
    return out


@pytest.fixture(scope="module")
def reviewer():
    return Reviewer(engine=None)      # no engine: the degraded path


class TestWithoutEngine:
    def test_review_still_names_the_opening(self, reviewer):
        moves = moves_from_san("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6")
        review = reviewer.review_moves(moves)
        assert review.opening is not None
        assert "Najdorf" in review.opening.name

    def test_accuracy_is_reported_as_unavailable(self, reviewer):
        review = reviewer.review_moves(moves_from_san("e4", "e5"))
        assert not review.engine_available
        assert "unavailable" in review.summary()

    def test_no_grades_are_invented(self, reviewer):
        review = reviewer.review_moves(moves_from_san("e4", "e5", "Nf3"))
        assert all(m.judgement is None for m in review.moves)

    def test_tracks_when_the_game_left_book(self, reviewer):
        moves = moves_from_san("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "h3", "h6", "a3")
        review = reviewer.review_moves(moves)
        assert review.last_book_ply > 0

    def test_illegal_move_stops_review_without_crashing(self, reviewer):
        moves = moves_from_san("e4", "e5") + [chess.Move.from_uci("a1a8")]
        review = reviewer.review_moves(moves)
        assert len(review.moves) == 2


class TestDeviation:
    def test_finds_the_move_that_left_the_repertoire(self, reviewer):
        """The roadmap's acceptance criterion: exact move number and expected move."""
        rep = Repertoire(name="Ruy", color=chess.WHITE)
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")

        moves = moves_from_san("e4", "e5", "Nf3", "Nc6", "Bc4")
        review = reviewer.review_moves(moves, color=chess.WHITE, rep=rep)

        assert review.deviation is not None
        assert review.deviation.move_number == 3
        assert review.deviation.played == "Bc4"
        assert review.deviation.expected == "Bb5"

    def test_no_deviation_when_in_book(self, reviewer):
        rep = Repertoire(name="Ruy", color=chess.WHITE)
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")
        review = reviewer.review_moves(
            moves_from_san("e4", "e5", "Nf3", "Nc6", "Bb5"), rep=rep
        )
        assert review.deviation is None
        assert "no deviation" in review.summary()

    def test_deviation_appears_in_the_summary(self, reviewer):
        rep = Repertoire(name="Ruy", color=chess.WHITE)
        rep.add_san_line("e4", "e5", "Nf3")
        review = reviewer.review_moves(moves_from_san("e4", "e5", "Nc3"), rep=rep)
        assert "Nf3" in review.summary()


class TestPgn:
    PGN = """[Event "Test"]
[White "Player"]
[Black "Engine"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1/2-1/2
"""

    def test_review_from_pgn_text(self, reviewer):
        game = chess.pgn.read_game(io.StringIO(self.PGN))
        review = reviewer.review_game(game)
        assert len(review.moves) == 6

    def test_review_from_file(self, reviewer, tmp_path):
        path = tmp_path / "g.pgn"
        path.write_text(self.PGN, encoding="utf-8")
        reviews = reviewer.review_pgn(str(path))
        assert len(reviews) == 1


class TestSuggestions:
    def test_suggests_repertoire_revision(self, reviewer):
        rep = Repertoire(name="Ruy", color=chess.WHITE)
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")
        review = reviewer.review_moves(
            moves_from_san("e4", "e5", "Nf3", "Nc6", "Bc4"), rep=rep
        )
        advice = suggest_study(review)
        assert any("repertoire" in a.lower() for a in advice)
        assert any("Bb5" in a for a in advice)

    def test_clean_game_gets_a_clean_verdict(self, reviewer):
        review = reviewer.review_moves(moves_from_san("e4", "e5"))
        assert suggest_study(review) == ["No significant errors found in this game."]
