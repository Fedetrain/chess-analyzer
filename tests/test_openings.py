"""Opening identification against the vendored ECO corpus."""

import chess
import pytest

from openings import OpeningBook, get_book, position_key


@pytest.fixture(scope="module")
def book() -> OpeningBook:
    return get_book()


def board_from_san(*moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


class TestCorpus:
    def test_corpus_is_large(self, book):
        """The whole point of the change: thousands of openings, not thirty."""
        assert len(book) > 2000

    def test_startpos_has_no_name(self, book):
        assert book.describe(chess.Board()) == "Starting position"


class TestIdentification:
    def test_najdorf(self, book):
        """The roadmap's acceptance criterion for this item."""
        board = board_from_san(
            "e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"
        )
        opening = book.identify(board)
        assert opening is not None
        assert opening.eco == "B90"
        assert "Najdorf" in opening.name
        assert opening.family == "Sicilian Defense"

    @pytest.mark.parametrize(
        "moves,expect_eco,expect_text",
        [
            (("e4", "e5", "Nf3", "Nc6", "Bb5"), "C60", "Ruy Lopez"),
            (("e4", "e5", "Nf3", "Nc6", "Bc4"), "C50", "Italian"),
            (("e4", "c6"), "B10", "Caro-Kann"),
            (("e4", "e6"), "C00", "French"),
            (("d4", "Nf6", "c4", "g6"), "E60", "Indian"),
            (("d4", "d5", "c4", "c6"), "D10", "Slav"),
        ],
    )
    def test_known_openings(self, book, moves, expect_eco, expect_text):
        opening = book.identify(board_from_san(*moves))
        assert opening is not None, moves
        assert opening.eco.startswith(expect_eco[0])
        assert expect_text.lower() in opening.name.lower()

    def test_falls_back_to_last_known_opening(self, book):
        """After leaving book the panel must still name where the game came from."""
        board = board_from_san("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6")
        for absurd in ("h3", "h6", "a3", "h5"):
            board.push_san(absurd)
        opening = book.identify(board)
        assert opening is not None
        assert "Najdorf" in opening.name


class TestTranspositions:
    def test_same_position_by_different_move_order(self, book):
        """Dropping the move counters from the key is what makes this work.

        Both orders reach the same position, but via a different last move, so
        their halfmove clocks differ and the raw FENs are NOT equal. A key that
        kept the counters would treat these as two separate openings.
        """
        a = board_from_san("d4", "Nf6", "c4", "e6", "Nf3")   # halfmove clock 1
        b = board_from_san("Nf3", "Nf6", "d4", "e6", "c4")   # halfmove clock 0

        assert a.fen() != b.fen()
        assert position_key(a) == position_key(b)

        found = book.lookup(a)
        assert found is not None
        assert found == book.lookup(b)

    def test_position_key_ignores_clocks(self):
        board = chess.Board()
        key_before = position_key(board)
        replayed = chess.Board(board.fen())
        assert position_key(replayed) == key_before

    def test_key_keeps_side_to_move(self):
        w = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        b = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1")
        assert position_key(w) != position_key(b)


class TestQueries:
    def test_continuations_from_start(self, book):
        moves = book.continuations(chess.Board())
        sans = {chess.Board().san(m) for m, _ in moves}
        assert {"e4", "d4", "Nf3", "c4"} <= sans

    def test_search_by_name(self, book):
        hits = book.search("Najdorf")
        assert hits
        assert all("najdorf" in o.name.lower() for o in hits)

    def test_search_empty_returns_nothing(self, book):
        assert book.search("   ") == []

    def test_family_line(self, book):
        line = book.family_line("Sicilian Defense")
        assert len(line) > 50
        assert line == sorted(line, key=lambda o: o.ply)

    def test_family_and_variation_split(self, book):
        board = board_from_san(
            "e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"
        )
        opening = book.identify(board)
        assert opening.family == "Sicilian Defense"
        assert "Najdorf" in opening.variation


class TestMissingData:
    def test_missing_directory_degrades_quietly(self, tmp_path):
        """No data must mean no names, never a crash."""
        empty = OpeningBook(directory=str(tmp_path))
        assert len(empty) == 0
        assert empty.describe(board_from_san("e4")) == "Out of book"
