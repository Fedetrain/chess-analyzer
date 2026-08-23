# drawing.py
import pygame
import chess
import math
from typing import Dict, Optional, Tuple, Any, List
from config import (
    BOARD_SIZE, SQUARE_SIZE, EVAL_BAR_WIDTH, EVAL_CAP,
    DIRTY_RECT_ENABLED, COLORS, PANEL_X, SCREEN_HEIGHT
)

class Drawing:
    """Rendering engine ottimizzato con nuovo stile."""
    
    def __init__(self, screen: pygame.Surface, piece_images: Dict[str, pygame.Surface]):
        self.screen = screen
        self.piece_images = piece_images
        self.dirty_rects: List[pygame.Rect] = []
        
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
                   dragging: Optional[Tuple] = None, selected: Optional[int] = None):
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

    def draw_eval_bar(self, analysis: Dict):
        rect = pygame.Rect(BOARD_SIZE, 0, EVAL_BAR_WIDTH, BOARD_SIZE)
        self.mark_dirty(rect)
        pygame.draw.rect(self.screen, (30,30,30), rect)
        
        val = analysis.get("evaluation", {}).get("value", 0)
        # Clamp e visualizzazione
        val = max(-EVAL_CAP, min(EVAL_CAP, val))
        white_pct = 0.5 + (val / (2*EVAL_CAP))
        h = int(BOARD_SIZE * white_pct)
        
        w_rect = pygame.Rect(BOARD_SIZE, BOARD_SIZE - h, EVAL_BAR_WIDTH, h)
        pygame.draw.rect(self.screen, (240,240,240), w_rect)
        pygame.draw.line(self.screen, (100,100,100), (BOARD_SIZE, BOARD_SIZE//2), (BOARD_SIZE+EVAL_BAR_WIDTH, BOARD_SIZE//2))

    def draw_arrow(self, start: Tuple[int,int], end: Tuple[int,int], color):
        pygame.draw.line(self.arrow_surf, color, start, end, 6)
        # Calcolo triangolo punta
        angle = math.atan2(start[1]-end[1], end[0]-start[0]) + math.pi/2
        p1 = (end[0] + 15*math.sin(angle), end[1] + 15*math.cos(angle))
        p2 = (end[0] + 15*math.sin(angle+2.5), end[1] + 15*math.cos(angle+2.5))
        p3 = (end[0] + 15*math.sin(angle-2.5), end[1] + 15*math.cos(angle-2.5))
        pygame.draw.polygon(self.arrow_surf, color, [end, p2, p3])

    def draw_best_move(self, orientation, analysis):
        self.arrow_surf.fill((0,0,0,0))
        if moves := analysis.get("top_moves"):
            try:
                m = chess.Move.from_uci(moves[0]['Move'])
                r1 = self.get_rect(m.from_square, orientation)
                r2 = self.get_rect(m.to_square, orientation)
                self.draw_arrow(r1.center, r2.center, COLORS.FRECCIA_MIGLIORE)
                self.mark_dirty(r1.union(r2))
            except: pass
        self.screen.blit(self.arrow_surf, (0,0))

    def mark_dirty(self, r):
        if DIRTY_RECT_ENABLED: self.dirty_rects.append(r)

    def redraw_all(self, board, orientation, last_move, selected, dragging, analysis, ui):
        self.draw_board(orientation)
        self.draw_highlights(board, orientation, last_move, selected, dragging)
        self.draw_pieces(board, orientation, dragging, selected)
        self.draw_eval_bar(analysis)
        self.draw_best_move(orientation, analysis)
        
        # UI Panel
        ui_rect = pygame.Rect(PANEL_X, 0, SCREEN_HEIGHT, SCREEN_HEIGHT) # W è gestita in ui
        self.mark_dirty(ui_rect)
        ui.draw(self.screen, board)
        
        if dragging:
            self.screen.blit(dragging[0], dragging[1])
            self.mark_dirty(dragging[1])

        if DIRTY_RECT_ENABLED and self.dirty_rects:
            pygame.display.update(self.dirty_rects)
            self.dirty_rects.clear()
        else:
            pygame.display.flip()