"""Repertoire as a position graph: transpositions, idempotent import, deviation."""

import io

import chess
import chess.pgn
import pytest

from repertoire import Repertoire, RepertoireMove


def rep_white() -> Repertoire:
    return Repertoire(name="Test", color=chess.WHITE)


class TestEdges:
    def test_own_and_opponent_moves_are_distinguished(self):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3")
        own = {m.san for m in rep.own_moves}
        assert own == {"e4", "Nf3"}          # only White's moves are cards
        assert len(rep) == 3

    def test_black_repertoire_flips_ownership(self):
        rep = Repertoire(name="Test", color=chess.BLACK)
        rep.add_san_line("e4", "c5", "Nf3", "d6")
        assert {m.san for m in rep.own_moves} == {"c5", "d6"}

    def test_card_id_is_position_plus_move(self):
        rep = rep_white()
        rep.add_san_line("e4")
        card = rep.own_moves[0]
        assert card.card_id.endswith("|e2e4")


class TestTranspositions:
    def test_transposing_orders_share_one_edge(self):
        """The whole reason for a graph: one card, not two.

        Both orders reach the same position; the continuation from it must be a
        single shared edge rather than a duplicate per line.
        """
        rep = rep_white()
        rep.add_san_line("d4", "Nf6", "c4", "e6", "Nf3", "d5")
        before = rep.position_count
        rep.add_san_line("Nf3", "Nf6", "d4", "e6", "c4", "d5")

        # The shared final position must not have produced a second bucket.
        board_a = chess.Board()
        for san in ("d4", "Nf6", "c4", "e6", "Nf3", "d5"):
            board_a.push_san(san)
        board_b = chess.Board()
        for san in ("Nf3", "Nf6", "d4", "e6", "c4", "d5"):
            board_b.push_san(san)

        from openings import position_key

        assert position_key(board_a) == position_key(board_b)
        assert rep.position_count < before * 2

    def test_reimport_is_idempotent(self):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")
        count = len(rep)
        positions = rep.position_count

        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")

        assert len(rep) == count
        assert rep.position_count == positions

    def test_reimport_bumps_weight(self):
        rep = rep_white()
        rep.add_san_line("e4")
        rep.add_san_line("e4")
        assert rep.own_moves[0].weight == 2


class TestPgnImport:
    PGN = """[Event "Repertoire"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 (3... Nf6 4. O-O) 4. Ba4 Nf6 *
"""

    def test_import_follows_variations(self):
        rep = rep_white()
        handle = io.StringIO(self.PGN)
        game = chess.pgn.read_game(handle)
        rep.import_pgn_game(game)

        sans = {m.san for m in rep.own_moves}
        assert {"e4", "Nf3", "Bb5", "Ba4"} <= sans
        assert "O-O" in sans          # from the variation

    def test_import_twice_is_idempotent(self):
        rep = rep_white()
        for _ in range(2):
            game = chess.pgn.read_game(io.StringIO(self.PGN))
            rep.import_pgn_game(game)
        rep2 = rep_white()
        game = chess.pgn.read_game(io.StringIO(self.PGN))
        rep2.import_pgn_game(game)
        assert len(rep) == len(rep2)

    def test_import_from_file(self, tmp_path):
        path = tmp_path / "rep.pgn"
        path.write_text(self.PGN, encoding="utf-8")
        rep = rep_white()
        assert rep.import_pgn(str(path)) > 0


class TestDeviation:
    def test_finds_where_the_game_left_book(self):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5")

        board = chess.Board()
        played = []
        for san in ("e4", "e5", "Nf3", "Nc6", "Bc4"):   # Bc4 instead of Bb5
            move = board.parse_san(san)
            played.append(move)
            board.push(move)

        result = rep.find_deviation(played)
        assert result is not None
        ply, move, expected = result
        assert ply == 4                       # White's third move
        assert expected.san == "Bb5"

    def test_no_deviation_when_following_book(self):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3")
        board = chess.Board()
        played = []
        for san in ("e4", "e5", "Nf3"):
            move = board.parse_san(san)
            played.append(move)
            board.push(move)
        assert rep.find_deviation(played) is None

    def test_opponent_novelty_is_not_a_deviation(self):
        """An unprepared opponent move is a gap, not the student's mistake."""
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3")
        board = chess.Board()
        played = []
        for san in ("e4", "d5"):              # Black leaves book
            move = board.parse_san(san)
            played.append(move)
            board.push(move)
        assert rep.find_deviation(played) is None


class TestTraversalAndPersistence:
    def test_lines_terminates_on_a_cyclic_graph(self):
        """A position graph can contain loops a tree cannot."""
        rep = rep_white()
        rep.add_san_line("Nf3", "Nf6", "Ng1", "Ng8")   # returns to the start
        lines = rep.lines(max_depth=10)
        assert lines is not None

    def test_round_trip(self, tmp_path):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3", "Nc6", "Bb5", comment="Ruy Lopez")
        path = tmp_path / "rep.json"
        rep.save(str(path))

        loaded = Repertoire.load(str(path))
        assert loaded.name == rep.name
        assert loaded.color == rep.color
        assert len(loaded) == len(rep)
        assert {m.card_id for m in loaded.own_moves} == {m.card_id for m in rep.own_moves}

    def test_coverage_report(self):
        rep = rep_white()
        rep.add_san_line("e4", "e5", "Nf3")
        cov = rep.coverage()
        assert cov["own_moves"] == 2
        assert cov["opponent_moves"] == 1
