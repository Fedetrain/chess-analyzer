# ui.py
import pygame
import chess
from typing import Dict, Any, Tuple, Optional, List
from config import (
    SCREEN_HEIGHT, ANALYSIS_PANEL_WIDTH, PANEL_X,
    ELO_LEVELS, DEFAULT_ELO_INDEX, COLORS, UCI_ELO_MIN
)

class UIManager:
    """Gestore Interfaccia Utente Moderna e Reattiva"""
    
    def __init__(self):
        self.panel_padding = 20
        self.button_height = 40
        
        # State containers
        self.game_state = ""
        self.status_text = ""
        self.judgement = None
        self.coach_text = ""
        self.current_analysis = None
        self.move_history_san: List[str] = []
        self.opening_name = ""
        self.accuracy = 0.0
        self.player_color: bool = chess.WHITE

        # FIX ELO Slider State
        self.current_elo = ELO_LEVELS[DEFAULT_ELO_INDEX]
        self.is_dragging_slider = False
        self.slider_drag_x = 0 # Posizione X temporanea durante il drag
        
        self.ui_rects: Dict[str, pygame.Rect] = {}
        
        self.init_fonts()
        self.init_layout()

    def init_fonts(self):
        try:
            # Prova a caricare font di sistema moderni
            base_font = "Segoe UI"
            self.fonts = {
                'title': pygame.font.SysFont(base_font, 26, bold=True),
                'header': pygame.font.SysFont(base_font, 20, bold=True),
                'body': pygame.font.SysFont(base_font, 16),
                'small': pygame.font.SysFont("Consolas", 14),
                'moves': pygame.font.SysFont(base_font, 15),
                'coach': pygame.font.SysFont(base_font, 16, italic=True),
                'opening': pygame.font.SysFont(base_font, 18, bold=True) # Font per Apertura
            }
        except:
            # Fallback
            self.fonts = {k: pygame.font.Font(None, s) for k,s in [('title',30), ('header',24), ('body',20), ('small',18), ('moves',18), ('coach',18), ('opening',22)]}

    def init_layout(self):
        """Layout ricalcolato per includere il box Apertura"""
        x = PANEL_X + self.panel_padding
        w = ANALYSIS_PANEL_WIDTH - (2 * self.panel_padding)
        y = SCREEN_HEIGHT - 70
        
        # Bottoni Navigazione (Fondo)
        btn_w = (w - 10) // 2
        self.ui_rects["undo"] = pygame.Rect(x, y, btn_w, self.button_height)
        self.ui_rects["new_game"] = pygame.Rect(x + btn_w + 10, y, btn_w, self.button_height)
        
        y -= 50
        self.ui_rects["flip"] = pygame.Rect(x, y, btn_w, self.button_height)
        self.ui_rects["color"] = pygame.Rect(x + btn_w + 10, y, btn_w, self.button_height)
        
        y -= 50
        self.ui_rects["save_pgn"] = pygame.Rect(x, y, w, self.button_height)
        
        # Slider ELO
        y_slider = y - 50
        self.ui_rects["slider_track"] = pygame.Rect(x, y_slider, w, 8)
        # Il knob è logico, non fisico qui
        self.ui_rects["slider_knob"] = pygame.Rect(x, y_slider - 8, 20, 24) 

    def handle_event(self, event) -> Optional[str]:
        """Gestione eventi ottimizzata per fluidità dello slider.

        Restituisce il nome dell'azione da eseguire (o None). L'applicazione
        dell'ELO al motore NON avviene qui: la UI espone soltanto il valore
        scelto in self.current_elo e segnala "slider_update"; è Game a
        propagarlo a EngineWrapper.set_elo (unico punto di applicazione).
        """

        if event.type == pygame.MOUSEBUTTONDOWN:
            p = event.pos

            if p[0] < PANEL_X:
                return None

            # Logica Slider
            track = self.ui_rects["slider_track"]
            slider_area = track.inflate(20, 30)

            if slider_area.collidepoint(p):
                self.is_dragging_slider = True
                self.slider_drag_x = max(track.left, min(p[0], track.right))
                return None

            # Altri bottoni
            for key, rect in self.ui_rects.items():
                if "slider" not in key and rect.collidepoint(p):
                    return key

        elif event.type == pygame.MOUSEBUTTONUP:
            if self.is_dragging_slider:
                self.is_dragging_slider = False
                self._apply_elo_change()
                return "slider_update"

        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging_slider:
                track = self.ui_rects["slider_track"]
                self.slider_drag_x = max(track.left, min(event.pos[0], track.right))
                return None  # Solo aggiornamento visivo

        return None

    def _apply_elo_change(self):
        """Aggancia la posizione del knob al livello ELO discreto più vicino."""
        track = self.ui_rects["slider_track"]
        pct = (self.slider_drag_x - track.left) / track.width
        idx = round(pct * (len(ELO_LEVELS) - 1))
        idx = max(0, min(len(ELO_LEVELS) - 1, idx))
        self.current_elo = ELO_LEVELS[idx]

    def update_state(self,
                     game_state: str,
                     status_text: str,
                     judgement,
                     coach_text: str,
                     current_analysis,
                     player_color: bool,
                     move_history_san: List[str],
                     opening_name: str,
                     accuracy: float) -> None:
        """Mirror the game's state into the UI. The UI owns no game state.

        Explicit assignments rather than ``self.__dict__.update(**kwargs)``: a
        typo in a field name would otherwise be accepted silently, creating a
        new attribute instead of updating the intended one.
        """
        self.game_state = game_state
        self.status_text = status_text
        self.judgement = judgement
        self.coach_text = coach_text
        self.current_analysis = current_analysis
        self.player_color = player_color
        self.move_history_san = move_history_san
        self.opening_name = opening_name
        self.accuracy = accuracy

    def draw(self, screen: pygame.Surface, board: chess.Board):
        pygame.draw.rect(screen, COLORS.PANEL, (PANEL_X, 0, ANALYSIS_PANEL_WIDTH, SCREEN_HEIGHT))

        x = PANEL_X + self.panel_padding
        y = 16
        w = ANALYSIS_PANEL_WIDTH - (2 * self.panel_padding)

        screen.blit(self.fonts['title'].render("Chess Analyzer", True, COLORS.TESTO), (x, y))
        y += 32
        col = COLORS.MIGLIORE if "Your turn" in self.status_text else COLORS.TESTO_SEC
        screen.blit(self.fonts['body'].render(self.status_text, True, col), (x, y))
        y += 32

        self.draw_info_box(screen, x, y, w, "Opening", self.opening_name or "-", COLORS.TESTO_ACCENT)
        y += 58

        self.draw_coach_bubble(screen, x, y, w)
        y += 128

        self.draw_technical_analysis(screen, x, y, w)
        y += 78

        self.draw_move_history(screen, x, y, w)

        self.draw_controls(screen)

    def draw_info_box(self, screen, x, y, w, label, value, color):
        """Disegna un box informativo (usato per le aperture)."""
        pygame.draw.rect(screen, (45,45,45), (x, y, w, 50), border_radius=8)
        lbl = self.fonts['small'].render(label.upper(), True, (120,120,120))
        screen.blit(lbl, (x+10, y+5))
        val = self.fonts['opening'].render(value, True, color)
        screen.blit(val, (x+10, y+22))

    #: Grade -> colour. Kept here so the palette stays a UI concern and the
    #: analysis layer needs no knowledge of pygame.
    GRADE_COLORS = {
        "Best": COLORS.MIGLIORE,
        "Book": COLORS.TESTO_ACCENT,
        "Excellent": COLORS.OTTIMA,
        "Good": COLORS.BUONA,
        "Inaccuracy": COLORS.IMPRECISIONE,
        "Mistake": COLORS.ERRORE,
        "Blunder": COLORS.GRAVE,
    }

    def draw_coach_bubble(self, screen, x, y, w):
        rect = pygame.Rect(x, y, w, 118)
        pygame.draw.rect(screen, (50, 50, 50), rect, border_radius=10)
        pygame.draw.rect(screen, (70, 70, 70), rect, width=1, border_radius=10)

        if self.judgement is not None:
            label = self.judgement.label
            colour = self.GRADE_COLORS.get(label, COLORS.TESTO)
            heading = f"{label}  ({self.judgement.accuracy:.0f}%)"
        else:
            colour, heading = COLORS.TESTO_SEC, "Coach"

        screen.blit(self.fonts['header'].render(heading, True, colour), (x + 10, y + 8))

        # The structure name is the single most useful line the coach produces:
        # it says what kind of position this is, not just how good it is.
        plan = getattr(self.judgement, "plan", None) if self.judgement else None
        offset = y + 34
        if plan is not None and plan.structure_name:
            screen.blit(
                self.fonts['small'].render(plan.structure_name, True, COLORS.TESTO_ACCENT),
                (x + 10, offset),
            )
            offset += 20

        self._draw_wrapped_text(
            screen, self.coach_text, x + 10, offset, w - 20, self.fonts['coach'], max_lines=4
        )

    def _draw_wrapped_text(self, screen, text, x, y, max_w, font, max_lines: int = 3):
        """Word-wrap semplice entro max_w pixel.

        La variabile di ciclo si chiama `word`: chiamandola `w` ombreggiava il
        parametro di larghezza dei chiamanti (draw_coach_bubble passa `w-20`),
        un bug latente che sarebbe scattato al primo uso di `w` dopo il loop.
        """
        lines = []
        curr = ""
        for word in text.split(' '):
            candidate = f"{curr}{word} "
            if not curr or font.size(candidate)[0] < max_w:
                curr = candidate
            else:
                lines.append(curr)
                curr = f"{word} "
        if curr:
            lines.append(curr)
        for i, line in enumerate(lines[:max_lines]):
            screen.blit(font.render(line, True, (220,220,220)), (x, y + i*20))

    def draw_technical_analysis(self, screen, x, y, w):
        analysis = self.current_analysis
        candidates = getattr(analysis, "candidates", None) or []
        mate_in = getattr(analysis, "mate_in", None)
        score = getattr(analysis, "score_white", 0)

        if not candidates:
            screen.blit(
                self.fonts['header'].render("Evaluation: -", True, COLORS.TESTO_SEC), (x, y)
            )
            return

        # Always shown from White's point of view, and labelled as such, so the
        # number can never be read in the wrong frame of reference.
        text = f"Mate in {abs(mate_in)}" if mate_in is not None else f"{score / 100:+.2f}"
        screen.blit(
            self.fonts['header'].render(f"Evaluation: {text} (White)", True, COLORS.TESTO), (x, y)
        )

        if self.accuracy:
            screen.blit(
                self.fonts['small'].render(
                    f"Session accuracy: {self.accuracy:.1f}%", True, COLORS.TESTO_SEC
                ),
                (x + 240, y + 4),
            )

        for i, candidate in enumerate(candidates[:3]):
            if candidate.mate_in is not None:
                value = f"M{abs(candidate.mate_in)}"
            else:
                value = f"{candidate.score_white / 100:+.2f}"
            line = f"{i + 1}. {candidate.uci}  ({value})"
            screen.blit(
                self.fonts['small'].render(line, True, COLORS.TESTO_SEC), (x, y + 26 + i * 17)
            )

    def draw_move_history(self, screen, x, y, w):
        title = self.fonts['body'].render("Moves", True, COLORS.TESTO_SEC)
        screen.blit(title, (x, y))
        
        history_rect = pygame.Rect(x, y+25, w, 80)
        pygame.draw.rect(screen, (35,35,35), history_rect, border_radius=4)
        
        # Mostra solo ultime 4 coppie (8 mosse) per evitare overflow
        start_idx = max(0, len(self.move_history_san) - 8)
        moves = self.move_history_san[start_idx:]
        
        px, py = x + 10, y + 30
        for i, m in enumerate(moves):
            # Logica per capire se è bianco o nero
            move_num = (start_idx + i)//2 + 1
            is_white = (start_idx + i) % 2 == 0
            
            if is_white:
                txt = f"{move_num}. {m}"
                col = COLORS.TESTO
            else:
                txt = f"{m}"
                col = (180,180,180)
                
            screen.blit(self.fonts['moves'].render(txt, True, col), (px, py))
            
            if not is_white: # A capo dopo mossa nera
                px = x + 10
                py += 20
            else: # Spazio dopo mossa bianca
                px = x + w//2

    def draw_controls(self, screen):
        track = self.ui_rects["slider_track"]
        knob = self.ui_rects["slider_knob"]
        
        # Track background
        pygame.draw.rect(screen, (60,60,60), track, border_radius=4)
        # Parte riempita (verde)
        filled_w = 0
        
        # Logica posizione visuale
        if self.is_dragging_slider:
            knob_center_x = self.slider_drag_x
            # Calcolo ELO temporaneo solo per visualizzarlo
            pct = (self.slider_drag_x - track.left) / track.width
            idx = round(pct * (len(ELO_LEVELS) - 1))
            display_elo = ELO_LEVELS[idx]
        else:
            # Posizione basata sullo stato reale
            try: idx = ELO_LEVELS.index(self.current_elo)
            except: idx = DEFAULT_ELO_INDEX
            pct = idx / (len(ELO_LEVELS) - 1)
            knob_center_x = track.left + (pct * track.width)
            display_elo = self.current_elo
            
        # Disegna parte riempita track
        filled_rect = pygame.Rect(track.left, track.top, knob_center_x - track.left, track.height)
        pygame.draw.rect(screen, COLORS.MIGLIORE, filled_rect, border_radius=4)
            
        # Disegna Knob
        knob_draw_rect = pygame.Rect(0, 0, 16, 16)
        knob_draw_rect.center = (knob_center_x, track.centery)
        pygame.draw.circle(screen, (240,240,240), knob_draw_rect.center, 8)
        
        # Below 1320 the engine has no calibrated Elo, so the label says so
        # rather than quoting a rating the engine cannot actually deliver.
        suffix = "" if display_elo >= UCI_ELO_MIN else " (approx.)"
        lbl = self.fonts['small'].render(
            f"Engine strength: {display_elo}{suffix}", True, COLORS.TESTO_SEC
        )
        screen.blit(lbl, (track.left, track.top - 20))
        
        # Buttons
        mp = pygame.mouse.get_pos()
        for name in ["undo", "new_game", "flip", "color", "save_pgn"]:
            label_txt = name.replace("_", " ").title()
            self.draw_btn(screen, label_txt, self.ui_rects[name], mp)

    def draw_btn(self, screen, text, rect, mouse_pos):
        hover = rect.collidepoint(mouse_pos)
        col = COLORS.SFONDO_BOTTONE_HOVER if hover else COLORS.SFONDO_BOTTONE
        pygame.draw.rect(screen, col, rect, border_radius=6)
        
        txt_surf = self.fonts['body'].render(text, True, COLORS.TESTO)
        txt_rect = txt_surf.get_rect(center=rect.center)
        screen.blit(txt_surf, txt_rect)