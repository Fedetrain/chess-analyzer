# structures.py
"""Pawn-structure recognition, computed from the board.

Why this module exists
----------------------
There is no open, structured data set of opening *plans* keyed by position.
Everything comprehensive is proprietary (see ``SOTA.md`` 2.5). So the "why" is
not downloaded here -- it is computed.

The key idea is to key plans on the **pawn structure** rather than on the
opening name. That is both more honest and far more general: the minority
attack is the plan in a Carlsbad structure whether you reached it from the
Queen's Gambit Exchange or from a Caro-Kann Panov, and an isolated queen's pawn
means the same thing however it appeared. One structure entry therefore covers
dozens of ECO codes, and it is derived from the position rather than asserted.

Everything in here is a fact about the board: which files are half-open, which
pawns are backward, which squares can never again be attacked by an enemy pawn.
None of it can hallucinate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import chess


class Structure(Enum):
    """Pawn structures the recogniser can name."""

    CARLSBAD = "Carlsbad"
    ISOLATED_QUEEN_PAWN = "Isolated queen's pawn"
    HANGING_PAWNS = "Hanging pawns"
    MAROCZY_BIND = "Maroczy bind"
    CLOSED_CHAIN = "Closed pawn chain"
    KINGS_INDIAN_CHAIN = "King's Indian chain"
    OPEN_SICILIAN = "Open Sicilian"
    OPEN_CENTRE = "Open centre"
    SCHEVENINGEN = "Small centre"
    SYMMETRICAL = "Symmetrical"
    UNRESOLVED = "Unresolved centre"

    def __str__(self) -> str:
        return self.value


@dataclass
class PawnFacts:
    """Everything computable about one side's pawns."""

    color: chess.Color
    files: set[int] = field(default_factory=set)
    doubled: list[int] = field(default_factory=list)
    isolated: list[int] = field(default_factory=list)
    backward: list[int] = field(default_factory=list)
    passed: list[chess.Square] = field(default_factory=list)
    half_open_files: list[int] = field(default_factory=list)
    islands: int = 0
    space: int = 0


@dataclass
class StructureReport:
    """The recogniser's verdict on a position."""

    structure: Structure = Structure.UNRESOLVED
    #: For one-sided structures (IQP, Maroczy), who owns the feature.
    owner: chess.Color | None = None
    white: PawnFacts = field(default_factory=lambda: PawnFacts(chess.WHITE))
    black: PawnFacts = field(default_factory=lambda: PawnFacts(chess.BLACK))
    outposts: dict[chess.Color, list[chess.Square]] = field(default_factory=dict)
    bad_bishop: dict[chess.Color, bool] = field(default_factory=dict)

    @property
    def name(self) -> str:
        if self.owner is None:
            return str(self.structure)
        side = "White" if self.owner == chess.WHITE else "Black"
        return f"{self.structure} ({side})"


def _pawn_squares(board: chess.Board, color: chess.Color) -> list[chess.Square]:
    return list(board.pieces(chess.PAWN, color))


def _files_of(squares: list[chess.Square]) -> list[int]:
    return [chess.square_file(sq) for sq in squares]


def _has_pawn_on(board: chess.Board, color: chess.Color, square: chess.Square) -> bool:
    piece = board.piece_at(square)
    return piece is not None and piece.piece_type == chess.PAWN and piece.color == color


def _count_islands(files: set[int]) -> int:
    if not files:
        return 0
    islands, previous = 1, min(files)
    for f in sorted(files)[1:]:
        if f - previous > 1:
            islands += 1
        previous = f
    return islands


def _is_backward(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """A pawn is backward when no friendly pawn can ever support it from behind.

    Implemented as: no friendly pawn on an adjacent file at or behind this
    pawn's rank, and the square in front is controlled by an enemy pawn.
    """
    file_, rank = chess.square_file(square), chess.square_rank(square)
    forward = 1 if color == chess.WHITE else -1

    for adj in (file_ - 1, file_ + 1):
        if not 0 <= adj <= 7:
            continue
        for sq in board.pieces(chess.PAWN, color):
            if chess.square_file(sq) != adj:
                continue
            r = chess.square_rank(sq)
            if (color == chess.WHITE and r <= rank) or (color == chess.BLACK and r >= rank):
                return False

    ahead_rank = rank + forward
    if not 0 <= ahead_rank <= 7:
        return False
    ahead = chess.square(file_, ahead_rank)
    return bool(board.attackers(not color, ahead) & board.pieces(chess.PAWN, not color))


def _is_passed(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    file_, rank = chess.square_file(square), chess.square_rank(square)
    for enemy in board.pieces(chess.PAWN, not color):
        ef, er = chess.square_file(enemy), chess.square_rank(enemy)
        if abs(ef - file_) > 1:
            continue
        if color == chess.WHITE and er > rank:
            return False
        if color == chess.BLACK and er < rank:
            return False
    return True


def _outposts(board: chess.Board, color: chess.Color) -> list[chess.Square]:
    """Advanced squares an enemy pawn can never attack again, that we do control.

    This is the computable half of "good knight, bad knight".
    """
    found: list[chess.Square] = []
    ranks = range(3, 6) if color == chess.WHITE else range(2, 5)
    enemy_pawns = board.pieces(chess.PAWN, not color)

    for rank in ranks:
        for file_ in range(8):
            sq = chess.square(file_, rank)
            if board.piece_at(sq) is not None and not _has_pawn_on(board, color, sq):
                pass
            # Can an enemy pawn ever attack this square?
            attackable = False
            for enemy in enemy_pawns:
                ef, er = chess.square_file(enemy), chess.square_rank(enemy)
                if abs(ef - file_) != 1:
                    continue
                if color == chess.WHITE and er > rank:
                    attackable = True
                if color == chess.BLACK and er < rank:
                    attackable = True
            if attackable:
                continue
            # And do we control it with a pawn?
            if board.attackers(color, sq) & board.pieces(chess.PAWN, color):
                found.append(sq)
    return found


def _bad_bishop(board: chess.Board, color: chess.Color) -> bool:
    """True when a side's own centre pawns sit on its bishop's colour.

    A bishop hemmed in by its owner's fixed pawns is the classic "bad piece",
    and unlike a plan it can be decided arithmetically.
    """
    bishops = board.pieces(chess.BISHOP, color)
    if not bishops:
        return False
    central = [
        sq for sq in board.pieces(chess.PAWN, color)
        if chess.square_file(sq) in (2, 3, 4, 5)
    ]
    if len(central) < 2:
        return False
    for bishop in bishops:
        light_bishop = (chess.square_file(bishop) + chess.square_rank(bishop)) % 2 == 1
        same_colour = sum(
            1 for sq in central
            if ((chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1) == light_bishop
        )
        if same_colour >= 3:
            return True
    return False


def _pawn_facts(board: chess.Board, color: chess.Color) -> PawnFacts:
    squares = _pawn_squares(board, color)
    files = _files_of(squares)
    file_set = set(files)
    enemy_files = set(_files_of(_pawn_squares(board, not color)))

    facts = PawnFacts(color=color, files=file_set)
    facts.doubled = sorted({f for f in file_set if files.count(f) > 1})
    facts.isolated = sorted(
        f for f in file_set if (f - 1) not in file_set and (f + 1) not in file_set
    )
    facts.backward = sorted(
        {chess.square_file(sq) for sq in squares if _is_backward(board, sq, color)}
    )
    facts.passed = [sq for sq in squares if _is_passed(board, sq, color)]
    facts.half_open_files = sorted(f for f in range(8) if f not in file_set and f in enemy_files)
    facts.islands = _count_islands(file_set)
    facts.space = sum(
        chess.square_rank(sq) if color == chess.WHITE else 7 - chess.square_rank(sq)
        for sq in squares
    )
    return facts


# ------------------------------------------------------------- recognisers


def _is_carlsbad(board: chess.Board) -> chess.Color | None:
    """White pawn d4, no white c-pawn; black pawn d5 and c-pawn, no black e-pawn.

    Arises from the Queen's Gambit Exchange and, by transposition, the Caro-Kann
    Panov and the Nimzo/QGD exchange lines.
    """
    wf = set(_files_of(_pawn_squares(board, chess.WHITE)))
    bf = set(_files_of(_pawn_squares(board, chess.BLACK)))

    if (
        _has_pawn_on(board, chess.WHITE, chess.D4)
        and 2 not in wf                                   # no white c-pawn
        and _has_pawn_on(board, chess.BLACK, chess.D5)
        and 2 in bf                                       # black keeps the c-pawn
        and 4 not in bf                                   # black has no e-pawn
    ):
        return chess.WHITE
    if (
        _has_pawn_on(board, chess.BLACK, chess.D5)
        and 2 not in bf
        and _has_pawn_on(board, chess.WHITE, chess.D4)
        and 2 in wf
        and 4 not in wf
    ):
        return chess.BLACK
    return None


def _iqp_owner(board: chess.Board) -> chess.Color | None:
    for color, square in ((chess.WHITE, chess.D4), (chess.BLACK, chess.D5)):
        files = set(_files_of(_pawn_squares(board, color)))
        if _has_pawn_on(board, color, square) and 2 not in files and 4 not in files:
            return color
    return None


def _hanging_pawns(board: chess.Board) -> chess.Color | None:
    """Pawns on c and d abreast, with no b- or e-pawn to support them."""
    for color, rank in ((chess.WHITE, 3), (chess.BLACK, 4)):
        files = set(_files_of(_pawn_squares(board, color)))
        if (
            _has_pawn_on(board, color, chess.square(2, rank))
            and _has_pawn_on(board, color, chess.square(3, rank))
            and 1 not in files
            and 4 not in files
        ):
            return color
    return None


def _maroczy(board: chess.Board) -> chess.Color | None:
    """White pawns on c4 and e4 against a black d-pawn and no black c-pawn."""
    bf = set(_files_of(_pawn_squares(board, chess.BLACK)))
    if (
        _has_pawn_on(board, chess.WHITE, chess.C4)
        and _has_pawn_on(board, chess.WHITE, chess.E4)
        and 2 not in bf
        and 3 in bf
    ):
        return chess.WHITE
    wf = set(_files_of(_pawn_squares(board, chess.WHITE)))
    if (
        _has_pawn_on(board, chess.BLACK, chess.C5)
        and _has_pawn_on(board, chess.BLACK, chess.E5)
        and 2 not in wf
        and 3 in wf
    ):
        return chess.BLACK
    return None


def _closed_chain(board: chess.Board) -> chess.Color | None:
    """The French/Advance chain: white e5 and d4 against black d5 and e6."""
    if (
        _has_pawn_on(board, chess.WHITE, chess.E5)
        and _has_pawn_on(board, chess.WHITE, chess.D4)
        and _has_pawn_on(board, chess.BLACK, chess.D5)
        and _has_pawn_on(board, chess.BLACK, chess.E6)
    ):
        return chess.WHITE
    if (
        _has_pawn_on(board, chess.BLACK, chess.E4)
        and _has_pawn_on(board, chess.BLACK, chess.D5)
        and _has_pawn_on(board, chess.WHITE, chess.D4)
        and _has_pawn_on(board, chess.WHITE, chess.E3)
    ):
        return chess.BLACK
    return None


def _kings_indian_chain(board: chess.Board) -> bool:
    """White d5 + e4 against black e5 + d6: the locked King's Indian centre."""
    return (
        _has_pawn_on(board, chess.WHITE, chess.D5)
        and _has_pawn_on(board, chess.WHITE, chess.E4)
        and _has_pawn_on(board, chess.BLACK, chess.E5)
        and _has_pawn_on(board, chess.BLACK, chess.D6)
    )


def _open_sicilian(board: chess.Board) -> bool:
    """White has traded the d-pawn for Black's c-pawn.

    The defining trade of the Open Sicilian, and the reason both sides get a
    half-open file pointing at the opposing king's side of the board: White down
    the d-file, Black down the c-file. Structurally the same whether the game
    became a Najdorf, a Dragon or a Classical.
    """
    wf = set(_files_of(_pawn_squares(board, chess.WHITE)))
    bf = set(_files_of(_pawn_squares(board, chess.BLACK)))
    return 4 in wf and 3 not in wf and 2 not in bf and 3 in bf


def _scheveningen(board: chess.Board) -> bool:
    """Black pawns on d6 and e6 against a white e-pawn: the small centre."""
    return (
        _has_pawn_on(board, chess.BLACK, chess.D6)
        and _has_pawn_on(board, chess.BLACK, chess.E6)
        and _has_pawn_on(board, chess.WHITE, chess.E4)
        and not _has_pawn_on(board, chess.WHITE, chess.D4)
    )


def analyse_structure(board: chess.Board) -> StructureReport:
    """Name the pawn structure and gather the supporting facts."""
    report = StructureReport(
        white=_pawn_facts(board, chess.WHITE),
        black=_pawn_facts(board, chess.BLACK),
    )
    report.outposts = {
        chess.WHITE: _outposts(board, chess.WHITE),
        chess.BLACK: _outposts(board, chess.BLACK),
    }
    report.bad_bishop = {
        chess.WHITE: _bad_bishop(board, chess.WHITE),
        chess.BLACK: _bad_bishop(board, chess.BLACK),
    }

    # Most specific first: a Carlsbad is also technically an unresolved centre.
    if (owner := _is_carlsbad(board)) is not None:
        report.structure, report.owner = Structure.CARLSBAD, owner
    elif (owner := _maroczy(board)) is not None:
        report.structure, report.owner = Structure.MAROCZY_BIND, owner
    elif (owner := _iqp_owner(board)) is not None:
        report.structure, report.owner = Structure.ISOLATED_QUEEN_PAWN, owner
    elif (owner := _hanging_pawns(board)) is not None:
        report.structure, report.owner = Structure.HANGING_PAWNS, owner
    elif (owner := _closed_chain(board)) is not None:
        report.structure, report.owner = Structure.CLOSED_CHAIN, owner
    elif _kings_indian_chain(board):
        report.structure = Structure.KINGS_INDIAN_CHAIN
    elif _scheveningen(board):
        report.structure = Structure.SCHEVENINGEN
    elif _open_sicilian(board):
        report.structure = Structure.OPEN_SICILIAN
    elif not (report.white.files & {3, 4}) and not (report.black.files & {3, 4}):
        report.structure = Structure.OPEN_CENTRE
    elif report.white.files == report.black.files and len(board.move_stack) > 4:
        report.structure = Structure.SYMMETRICAL
    else:
        report.structure = Structure.UNRESOLVED

    return report
