import chess
import chess.pgn
import os
import datetime
from typing import Optional

class PGNHandler:
    """Gestisce la creazione e il salvataggio di file PGN."""
    
    def save_game(self, board: chess.Board, pgn_dir: str, player_color: int) -> Optional[str]:
        """
        Salva la cronologia della partita corrente in un file PGN.
        Usa chess.pgn.Game.from_board(board) che ricostruisce la partita
        dalla mossa iniziale fino allo stato attuale.
        """
        if not board.move_stack:
            print("Nessuna mossa da salvare.")
            return None

        # Crea un oggetto Game PGN dalla scacchiera
        game = chess.pgn.Game.from_board(board)
        
        # Imposta gli header PGN
        game.headers["Event"] = "Partita di Analisi"
        game.headers["Site"] = "Analizzatore Scacchi Stockfish"
        game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        
        if player_color == chess.WHITE:
            game.headers["White"] = "Umano"
            game.headers["Black"] = "Stockfish"
        else:
            game.headers["White"] = "Stockfish"
            game.headers["Black"] = "Umano"
            
        game.headers["Round"] = "1"
        game.headers["Result"] = board.result()

        # Genera un nome file univoco
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"partita_{timestamp}.pgn"
        filepath = os.path.join(pgn_dir, filename)

        try:
            # Assicurati che la directory esista
            os.makedirs(pgn_dir, exist_ok=True)
            
            # Scrivi il file
            with open(filepath, "w", encoding="utf-8") as f:
                exporter = chess.pgn.FileExporter(f)
                game.accept(exporter)
                
            print(f"Partita salvata in: {filepath}")
            return filename
        except Exception as e:
            print(f"Errore durante il salvataggio del PGN: {e}")
            return None