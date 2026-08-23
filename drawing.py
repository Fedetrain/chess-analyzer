# drawing.py
import math

import chess
import pygame

from config import BOARD_SIZE, COLORS, EVAL_BAR_WIDTH, EVAL_CAP, PANEL_X, SCREEN_HEIGHT, SQUARE_SIZE


class Drawing:
    """Rendering engine ottimizzato con nuovo stile."""

    def __init__(self, screen: pygame.Surface, piece_images: dict[str, pygame.Surface]):
        self.screen = screen
        self.piece_images = piece_images
        self.dirty_rects: list[pygame.Rect] = []

        # Surfaces
        self.highlight_surf = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
        self.arrow_surf = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)

        try:
            self.font = pygame.font.SysFont("Segoe UI", 12, bold=True)
        except:
            self.font = pygame.font.Font(None, 14)

    def get_rect(self, square: int, orientation: int) -> pygame.Rect:
        f = chess.square_file(square)
        r = chess.square_rank(square)
        if orientation == chess.WHITE:
            return pygame.Rect(f*SQUARE_SIZE, (7-r)*SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)
        return pygame.Rect((7-f)*SQUARE_SIZE, r*SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)

    def draw_board(self, orientation: int):
        self.mark_dirty(pygame.Rect(0,0,BOARD_SIZE,BOARD_SIZE))
        for r in range(8):
            for f in range(8):
                color = COLORS.BIANCO if (r+f)%2==0 else COLORS.NERO
                if orientation == chess.WHITE:
                    x, y = f*SQUARE_SIZE, r*SQUARE_SIZE
                else:
                    x, y = (7-f)*SQUARE_SIZE, (7-r)*SQUARE_SIZE
                pygame.draw.rect(self.screen, color, (x,y,SQUARE_SIZE,SQUARE_SIZE))

        # Coordinate
        coords = "abcdefgh" if orientation == chess.WHITE else "hgfedcba"
        nums = "87654321" if orientation == chess.WHITE else "12345678"
        for i in range(8):
            # Numeri a sinistra
            col = COLORS.NERO if i%2==0 else COLORS.BIANCO
            txt = self.font.render(nums[i], True, col)
            self.screen.blit(txt, (2, i*SQUARE_SIZE + 2))
            # Lettere in basso
            col = COLORS.NERO if i%2!=0 else COLORS.BIANCO
            txt = self.font.render(coords[i], True, col)
            self.screen.blit(txt, (i*SQUARE_SIZE + SQUARE_SIZE - 10, BOARD_SIZE - 16))

    def draw_pieces(self, board: chess.Board, orientation: int,
                   dragging: tuple | None = None, selected: int | None = None):
        drag_sq = selected if dragging else None
        for sq in chess.SQUARES:
            if sq == drag_sq: continue
            piece = board.piece_at(sq)
            if piece:
                key = ('w' if piece.color else 'b') + piece.symbol().upper()
                if img := self.piece_images.get(key):
                    rect = self.get_rect(sq, orientation)
                    self.screen.blit(img, rect)
                    self.mark_dirty(rect)

    def draw_highlights(self, board, orientation, last_move, selected, dragging):
        self.highlight_surf.fill((0,0,0,0))

        if last_move:
            for sq in [last_move.from_square, last_move.to_square]:
                r = self.get_rect(sq, orientation)
                pygame.draw.rect(self.highlight_surf, COLORS.HIGHLIGHT_LAST_MOVE, r)
                self.mark_dirty(r)

        if board.is_check():
            if k := board.king(board.turn):
                r = self.get_rect(k, orientation)
                pygame.draw.rect(self.highlight_surf, COLORS.HIGHLIGHT_CHECK, r)
                self.mark_dirty(r)

        if selected is not None and not dragging:
            r = self.get_rect(selected, orientation)
            pygame.draw.rect(self.highlight_surf, COLORS.HIGHLIGHT_SELECTED, r)
            self.mark_dirty(r)

            for m in board.legal_moves:
                if m.from_square == selected:
                    dest = self.get_rect(m.to_square, orientation)
                    cx, cy = dest.center
                    if board.is_capture(m):
                        pygame.draw.circle(self.highlight_surf, COLORS.HIGHLIGHT_LEGAL_CAPTURE, (cx,cy), SQUARE_SIZE//2, 5)
                    else:
                        pygame.draw.circle(self.highlight_surf, COLORS.HIGHLIGHT_LEGAL_MOVE, (cx,cy), SQUARE_SIZE//6)
                    self.mark_dirty(dest)

        self.screen.blit(self.highlight_surf, (0,0))

    def draw_eval_bar(self, analysis, orientation: int = chess.WHITE):
        """Draw the evaluation bar.

        The score comes in already expressed from White's point of view
        (``Analysis.score_white``). The previous implementation read a
        side-to-move relative score and rendered it as if it were White's, so
        the bar was inverted on every position with Black to move -- half the
        game. Mates were also read as centipawns, so a mate in 3 drew a bar at
        roughly equality.
        """
        rect = pygame.Rect(BOARD_SIZE, 0, EVAL_BAR_WIDTH, BOARD_SIZE)
        self.mark_dirty(rect)
        pygame.draw.rect(self.screen, COLORS.EVAL_BG, rect)

        score = getattr(analysis, "score_white", 0)
        mate_in = getattr(analysis, "mate_in", None)

        if mate_in is not None:
            white_share = 1.0 if mate_in > 0 else 0.0
        else:
            clamped = max(-EVAL_CAP, min(EVAL_CAP, score))
            white_share = 0.5 + (clamped / (2 * EVAL_CAP))

        white_height = int(BOARD_SIZE * white_share)
        # The bar is drawn from whichever end the player's own colour sits at,
        # so it stays intuitive after flipping the board.
        if orientation == chess.WHITE:
            white_rect = pygame.Rect(
                BOARD_SIZE, BOARD_SIZE - white_height, EVAL_BAR_WIDTH, white_height
            )
        else:
            white_rect = pygame.Rect(BOARD_SIZE, 0, EVAL_BAR_WIDTH, white_height)
        pygame.draw.rect(self.screen, (240, 240, 240), white_rect)

        pygame.draw.line(
            self.screen, (100, 100, 100),
            (BOARD_SIZE, BOARD_SIZE // 2),
            (BOARD_SIZE + EVAL_BAR_WIDTH, BOARD_SIZE // 2),
        )

    def draw_arrow(self, start: tuple[int, int], end: tuple[int, int], color):
        """Draw a line from *start* to *end* with an arrowhead at the end."""
        pygame.draw.line(self.arrow_surf, color, start, end, 6)

        angle = math.atan2(start[1] - end[1], end[0] - start[0]) + math.pi / 2
        left = (end[0] + 15 * math.sin(angle + 2.5), end[1] + 15 * math.cos(angle + 2.5))
        right = (end[0] + 15 * math.sin(angle - 2.5), end[1] + 15 * math.cos(angle - 2.5))
        pygame.draw.polygon(self.arrow_surf, color, [end, left, right])

    def draw_best_move(self, orientation, analysis):
        self.arrow_surf.fill((0, 0, 0, 0))
        best = getattr(analysis, "best", None)
        if best is not None:
            r1 = self.get_rect(best.move.from_square, orientation)
            r2 = self.get_rect(best.move.to_square, orientation)
            self.draw_arrow(r1.center, r2.center, COLORS.FRECCIA_MIGLIORE)
            self.mark_dirty(r1.union(r2))
        self.screen.blit(self.arrow_surf, (0, 0))

    def mark_dirty(self, r):
        """No-op hook kept for the partial-redraw path, which is not enabled.

        The full redraw costs little at this board size and removes a whole
        class of stale-pixel bugs, so the dirty-rect flag that used to gate this
        has been deleted rather than left as dead configuration.
        """

    def redraw_all(self, board, orientation, last_move, selected, dragging, analysis, ui):
        self.draw_board(orientation)
        self.draw_highlights(board, orientation, last_move, selected, dragging)
        self.draw_pieces(board, orientation, dragging, selected)
        self.draw_eval_bar(analysis, orientation)
        self.draw_best_move(orientation, analysis)

        # UI Panel
        ui_rect = pygame.Rect(PANEL_X, 0, SCREEN_HEIGHT, SCREEN_HEIGHT) # W è gestita in ui
        self.mark_dirty(ui_rect)
        ui.draw(self.screen, board)

        if dragging:
            self.screen.blit(dragging[0], dragging[1])
            self.mark_dirty(dragging[1])

        pygame.display.flip()
