"""The 'why' engine: structure recognition and plan explanation, fully offline."""

import chess
import pytest

from analysis import Grade, Judgement
from coach import Coach, PlanLibrary, wikibooks_url
from structures import Structure, analyse_structure


def board_from_san(*moves: str) -> chess.Board:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board


@pytest.fixture(scope="module")
def coach() -> Coach:
    return Coach()


# --------------------------------------------------------------- structures


class TestStructureRecognition:
    def test_carlsbad(self):
        """The roadmap's acceptance criterion for this item."""
        board = board_from_san("d4", "d5", "c4", "e6", "Nc3", "Nf6", "cxd5", "exd5")
        report = analyse_structure(board)
        assert report.structure is Structure.CARLSBAD
        assert report.owner == chess.WHITE

    def test_isolated_queen_pawn(self):
        board = chess.Board("rnbqkb1r/pp3ppp/4pn2/8/3P4/5N2/PP3PPP/RNBQKB1R w KQkq - 0 7")
        report = analyse_structure(board)
        assert report.structure is Structure.ISOLATED_QUEEN_PAWN
        assert report.owner == chess.WHITE

    def test_french_closed_chain(self):
        board = board_from_san("e4", "e6", "d4", "d5", "e5")
        report = analyse_structure(board)
        assert report.structure is Structure.CLOSED_CHAIN
        assert report.owner == chess.WHITE

    def test_kings_indian_chain(self):
        board = chess.Board("rnbq1rk1/ppp2pbp/3p1np1/3Pp3/4P3/2N2N2/PPP2PPP/R1BQKB1R w KQ - 0 7")
        assert analyse_structure(board).structure is Structure.KINGS_INDIAN_CHAIN

    def test_open_centre(self):
        board = chess.Board("rnbqkbnr/ppp2ppp/8/8/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 5")
        assert analyse_structure(board).structure is Structure.OPEN_CENTRE

    def test_startpos_is_not_misidentified(self):
        report = analyse_structure(chess.Board())
        assert report.structure in (Structure.SYMMETRICAL, Structure.UNRESOLVED)


class TestComputedFacts:
    def test_detects_isolated_pawn(self):
        board = chess.Board("4k3/8/8/8/8/8/3P4/4K3 w - - 0 1")
        report = analyse_structure(board)
        assert 3 in report.white.isolated

    def test_detects_doubled_pawns(self):
        board = chess.Board("4k3/8/8/8/8/3P4/3P4/4K3 w - - 0 1")
        assert 3 in analyse_structure(board).white.doubled

    def test_detects_passed_pawn(self):
        board = chess.Board("4k3/8/8/3P4/8/8/8/4K3 w - - 0 1")
        report = analyse_structure(board)
        assert chess.D5 in report.white.passed

    def test_pawn_blocked_by_enemy_is_not_passed(self):
        board = chess.Board("4k3/3p4/8/3P4/8/8/8/4K3 w - - 0 1")
        report = analyse_structure(board)
        assert chess.D5 not in report.white.passed

    def test_half_open_file(self):
        """White has no e-pawn, Black does: the e-file is half-open for White."""
        board = board_from_san("e4", "d5", "exd5")
        report = analyse_structure(board)
        assert 4 in report.white.half_open_files

    def test_pawn_islands(self):
        board = chess.Board()
        assert analyse_structure(board).white.islands == 1


# -------------------------------------------------------------------- coach


class TestBriefing:
    def test_carlsbad_briefing_names_the_minority_attack(self, coach):
        """The full acceptance criterion: correct structure AND correct plan,
        for both colours, with no network."""
        board = board_from_san("d4", "d5", "c4", "e6", "Nc3", "Nf6", "cxd5", "exd5")
        briefing = coach.brief(board)

        assert "Carlsbad" in briefing.structure_name
        assert briefing.summary

        white_plan = " ".join(briefing.plans_white).lower()
        black_plan = " ".join(briefing.plans_black).lower()

        assert "minority attack" in white_plan
        assert "b4" in white_plan or "b5" in white_plan
        assert "kingside" in black_plan or "c5" in black_plan

        assert briefing.typical_mistakes
        assert briefing.good_pieces

    def test_iqp_briefing_tells_both_sides_the_opposite_thing(self, coach):
        """The owner wants pieces on, the blockader wants them off."""
        board = chess.Board("rnbqkb1r/pp3ppp/4pn2/8/3P4/5N2/PP3PPP/RNBQKB1R w KQkq - 0 7")
        briefing = coach.brief(board)

        owner = " ".join(briefing.plans_white).lower()
        defender = " ".join(briefing.plans_black).lower()

        assert "keep pieces on" in owner or "avoid trading" in owner
        assert "blockade" in defender
        assert "trade" in defender

    def test_briefing_reports_board_facts(self, coach):
        board = board_from_san("e4", "d5", "exd5")
        briefing = coach.brief(board)
        assert any("half-open" in o for o in briefing.observations)

    def test_briefing_names_the_opening(self, coach):
        board = board_from_san("e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6")
        briefing = coach.brief(board)
        assert briefing.opening is not None
        assert "Najdorf" in briefing.opening.name

    def test_every_structure_has_a_library_entry(self):
        """A structure the recogniser can name but the library cannot explain
        would leave the coach silent."""
        library = PlanLibrary()
        for structure in Structure:
            entry = library.for_structure(structure)
            assert entry, f"no plans for {structure}"
            assert entry.get("summary")
            assert entry.get("owner_plans")
            assert entry.get("opponent_plans")


class TestWikibooksLink:
    def test_root_for_startpos(self):
        assert wikibooks_url(chess.Board()).endswith("Chess_Opening_Theory")

    def test_encodes_the_move_path(self):
        url = wikibooks_url(board_from_san("e4", "c5", "Nf3"))
        assert "1._e4" in url
        assert "1...c5" in url
        assert "2._Nf3" in url

    def test_is_derived_not_fetched(self):
        """Building the link must never touch the network."""
        url = wikibooks_url(board_from_san("d4", "d5"))
        assert url.startswith("https://en.wikibooks.org/")


class TestAnnotation:
    def test_book_move_is_labelled_theory(self, coach):
        board = board_from_san("e4", "c5", "Nf3")
        move = board.parse_san("d6")
        judgement = Judgement(move=move, san="d6", grade=Grade.EXCELLENT)
        coach.annotate(judgement, board, move)
        assert judgement.is_book
        assert "Theory" in judgement.explanation

    def test_castling_is_described(self, coach):
        board = board_from_san("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")
        move = board.parse_san("O-O")
        judgement = Judgement(move=move, san="O-O", grade=Grade.EXCELLENT)
        coach.annotate(judgement, board, move)
        assert "safety" in judgement.explanation.lower()

    def test_blunder_names_the_better_move(self, coach):
        board = board_from_san("e4", "e5")
        move = board.parse_san("Nf3")
        judgement = Judgement(
            move=move, san="Nf3", grade=Grade.BLUNDER,
            win_loss=25.0, best_san="d4",
        )
        coach.annotate(judgement, board, move)
        assert "d4" in judgement.explanation

    def test_annotation_attaches_a_briefing(self, coach):
        board = board_from_san("d4", "d5", "c4", "e6", "Nc3", "Nf6", "cxd5")
        move = board.parse_san("exd5")
        judgement = Judgement(move=move, san="exd5")
        coach.annotate(judgement, board, move)
        assert judgement.plan is not None
        assert "Carlsbad" in judgement.plan.structure_name

    def test_explanation_is_never_empty(self, coach):
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"):
            move = board.parse_san(san)
            judgement = Judgement(move=move, san=san)
            coach.annotate(judgement, board, move)
            assert judgement.explanation.strip()
            board.push(move)
