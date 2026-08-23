# main.py
import pygame
import sys
from game import Game
from config import STOCKFISH_PATH, STOCKFISH_MISSING_MESSAGE

def main():
    """Funzione principale per avviare il gioco."""

    print("="*60)
    print("Chess Analyzer")

    if STOCKFISH_PATH:
        print(f"Stockfish engine: {STOCKFISH_PATH}")
    else:
        print(STOCKFISH_MISSING_MESSAGE)
        print("")
        print("The GUI will still start, but the analysis panel and the AI")
        print("opponent stay inactive until an engine is configured.")
    print("="*60)

    try:
        game = Game()
        game.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    main()