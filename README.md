# Chess Analyzer

**Play against Stockfish with chess.com-style real-time move analysis.**

[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-5%20passing-brightgreen.svg)](#testing)
[![Engine](https://img.shields.io/badge/engine-Stockfish%20(UCI)-lightgrey.svg)](https://stockfishchess.org/)

A desktop chess GUI built with Pygame and `python-chess`. It drives an external
Stockfish process over UCI and turns its output into the feedback layer you
expect from an online analysis board: a live evaluation bar, a best-move arrow,
and a graded verdict on every move you play — computed the moment you play it,
not at the end of the game.

---

## Features

![Chess Analyzer screenshot](docs/screenshot.png)

<!-- Drop a 1144x720 capture of the running app at docs/screenshot.png -->

- **Live evaluation bar** — Stockfish's score for the current position, clamped
  to ±10 pawns and rendered as a vertical white/black split next to the board.
- **Best-move arrow** — the engine's principal variation drawn straight on the
  board, with the top 3 candidate moves and their scores listed in the panel.
- **Move classification** — every human move is graded *Migliore / Ottima /
  Buona / Imprecisione / Errore / Grave Errore* from its centipawn loss, with
  configurable thresholds. See [the pipeline](#move-classification-pipeline).
- **Heuristic coach** — a short natural-language explanation of *why* the move
  scored the way it did, derived from board features (centre control, minor
  piece development, castling, captures, checks, checkmate).
- **Opening recognition** — a dual database: longest-prefix matching over UCI
  move sequences, with an exact-FEN table as a fallback for transpositions.
- **Adjustable engine strength** — an ELO slider from 800 to 3200, snapped to
  eight discrete levels and applied to Stockfish's `UCI_Elo` / `UCI_LimitStrength`.
- **Board interaction** — click-to-move or drag-and-drop, legal-move dots,
  capture rings, check and last-move highlights, board flip, play as either colour.
- **Undo** — rolls back the human/engine move pair and re-runs the analysis.
- **PGN export** — saves the current game with full headers to `partite_pgn/`.
- **Non-blocking UI** — engine startup, position analysis and the AI reply all
  run on worker threads; the 60 FPS render loop never waits on Stockfish.

> The in-app panel text and coach explanations are in Italian; the codebase,
> configuration and this documentation are in English.

---

## Move classification pipeline

Classification happens in `EngineWrapper.classify_move` and is a pure function
of two engine queries: the analysis of the position **before** the move, and the
evaluation of the position **after** it.

### 1. Two queries, two frames of reference

| Query | Position | Frame of reference |
|---|---|---|
| `get_analysis(fen_before)` | before the move | side to move = **the player** |
| `evaluate_position(fen_after)` | after the move | side to move = **the opponent** |

Stockfish always reports scores from the point of view of the side to move.
The two queries therefore sit in opposite frames, and the second must be negated
before the two can be compared.

The FEN is set explicitly on the engine before each query. This matters: the UCI
session is stateful, and the GUI queries the engine from more than one thread
(background analysis and the AI turn). Reading an evaluation without first
setting the position returns the score of whatever position another thread
happened to load last. All position→query sequences are serialised behind a
lock inside `EngineWrapper`, and the pre-move analysis carries the FEN it was
computed for so that a stale cached result can be detected and recomputed.

### 2. Mate score normalisation

Mate announcements are not centipawn values, so both `_normalize_score`
(top-move entries) and `_normalize_eval` (evaluation dicts) project them onto
the same scale before any arithmetic:

```
mate in +N  ->   MATE_SCORE - 100 * |N|      # faster mate = higher score
mate in -N  ->  -MATE_SCORE + 100 * |N|      # being mated = symmetric penalty
```

with `MATE_SCORE = 10000`. Subtracting `100 * |N|` keeps a mate in 2 strictly
better than a mate in 5, and keeps every mate strictly above any material
evaluation, so mate lines and centipawn lines can be compared with `-`.

### 3. Centipawn loss

```python
score_best   =  normalize(analysis_before.top_moves[0])   # player's POV
score_actual = -normalize(eval_after)                     # negated into player's POV
loss         =  max(0, score_best - score_actual)         # centipawns
```

The `max(0, …)` clamp matters in practice: the pre-move analysis runs at
`DEPTH_FAST_ANALYSIS` while the post-move evaluation can resolve a tactic the
shallower search missed, which would otherwise yield a *negative* loss — a
player being penalised for outplaying the shallow search.

### 4. Thresholds

Loss is compared against ascending thresholds (`config.py`, centipawns). A move
that matches the engine's own first choice is labelled *Migliore* regardless of
the computed loss, which absorbs depth-mismatch noise at the top of the scale.

| Label | Condition | Constant |
|---|---|---|
| ★ Migliore | engine's top move, or `loss ≤ 5` | `SOGLIA_MIGLIORE` |
| Ottima | `loss ≤ 15` | `SOGLIA_OTTIMA` |
| Buona | `loss ≤ 35` | `SOGLIA_BUONA` |
| Imprecisione | `loss ≤ 70` | `SOGLIA_IMPRECISIONE` |
| Errore | `loss ≤ 150` | `SOGLIA_ERRORE` |
| Grave Errore | `loss > 150` | — |

Every threshold is a module-level constant; tightening the scale is a one-line
edit in `config.py`.

---

## The heuristic coach

The numeric label answers *how bad*, not *why*. `ChessInstructor.explain_move`
adds the second half by extracting board features from the position pair and
selecting a phrasing template:

| Feature | Derivation |
|---|---|
| Centre control | destination square ∈ {d4, e4, d5, e5} |
| Minor piece development | knight/bishop leaving its own back rank |
| King safety | `board_after.is_castling(move)` |
| Capture / check / mate | `is_capture`, `is_check`, `is_checkmate` |

The classification label selects the register (praise, caution, warning) and the
strongest matching feature selects the specific sentence, so an *Ottima* castling
move and an *Ottima* central pawn push produce different explanations rather
than a generic one. This is deliberately heuristic — it is a readable gloss on
the engine's number, not a second engine.

---

## Opening recognition

`ChessUtils.identify_opening` runs two passes and short-circuits after 20 plies:

1. **UCI sequence matching** — the move stack is flattened to a UCI string and
   matched against `OPENINGS_SEQUENCES`, iterated longest-key-first so that
   `e2e4 e7e5 g1f3 b8c6 f1b5` (Ruy Lopez) wins over any shorter prefix.
2. **Exact FEN lookup** — the first four FEN fields (placement, side to move,
   castling rights, en-passant square) are matched against `OPENINGS_FEN_DB`.
   Dropping the move counters makes this pass transposition-aware: the same
   position reached by a different move order still resolves.

Anything unmatched degrades gracefully to *Apertura non comune* / *Medio Gioco*.

---

## Architecture

Nine flat modules, each with one responsibility and no circular imports.
`config.py` is the only module everything else depends on.

| Module | Responsibility |
|---|---|
| `main.py` | Entry point; resolves and reports the engine path, owns the crash handler |
| `config.py` | `UIColors` dataclass, layout/engine/threshold constants, Stockfish path resolution |
| `engine.py` | `EngineWrapper`: UCI session, LRU-cached analysis, `classify_move`, score normalisation |
| `game.py` | Game loop, board state, input→move translation, worker threads, `AssetManager` |
| `drawing.py` | Board, pieces, highlights, evaluation bar, best-move arrow |
| `ui.py` | `UIManager`: analysis panel, coach bubble, move list, ELO slider, buttons |
| `chess_utils.py` | Opening databases, `ChessInstructor`, `AnalysisCache`, cached legal moves |
| `pgn_handler.py` | PGN construction and export |
| `test_chess_utils.py` | Unit tests for the caching layer |

**Threading model.** The main thread does nothing but poll events and render at
60 FPS. Engine construction, position analysis and the AI reply each run on a
daemon worker. Shared state is exchanged through plain attributes guarded by
FEN identity checks — a worker writes its result only if the board still holds
the position the work was started for — while access to the Stockfish process
itself is serialised by a reentrant lock in `EngineWrapper`.

**Caching.** `AnalysisCache` is an LRU cache with a TTL, keyed by
`f"{fen}_{depth}"`, so revisiting a position via undo is free until entries
expire. Legal move generation is separately memoised with `functools.lru_cache`.

---

## Quick start

**Requirements:** Python 3.8+ and a Stockfish binary.

```bash
git clone https://github.com/Fedetrain/chess-analyzer.git
cd chess-analyzer

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Download the engine from **<https://stockfishchess.org/download/>** and point the
application at it:

```bash
# Linux / macOS
export STOCKFISH_PATH=/usr/local/bin/stockfish

# Windows (PowerShell)
$env:STOCKFISH_PATH = "C:\engines\stockfish.exe"
```

If `STOCKFISH_PATH` is unset, the application falls back to a `stockfish`
executable on `PATH` (so `brew install stockfish` or
`apt install stockfish` needs no configuration at all). If neither resolves, the
GUI still starts and prints setup instructions; analysis stays inactive.

```bash
python main.py
```

### Controls

| Action | How |
|---|---|
| Move | Click origin then destination, or drag the piece |
| Undo | **Undo** — rolls back both your move and the engine's reply |
| New game | **New Game** |
| Flip board | **Flip** |
| Switch colour | **Color** — swaps sides and restarts |
| Save PGN | **Save Pgn** — writes to `partite_pgn/` |
| Engine strength | Drag the ELO slider (800–3200) |

---

## Testing

The test suite covers the caching layer and the memoised move generator; it
needs no engine binary and no display.

```bash
python -m unittest test_chess_utils -v
```

```
test_basic_operations (TestAnalysisCache) ... ok
test_lru_eviction (TestAnalysisCache) ... ok
test_timeout (TestAnalysisCache) ... ok
test_cache_different_positions (TestChessUtils) ... ok
test_legal_moves_cached (TestChessUtils) ... ok

Ran 5 tests in 1.102s

OK
```

---

## Configuration

Everything tunable lives in `config.py`:

| Constant | Default | Effect |
|---|---|---|
| `BOARD_SIZE` | `720` | Board edge in pixels; the window sizes itself from this |
| `ANALYSIS_PANEL_WIDTH` | `400` | Width of the right-hand panel |
| `DEPTH_FAST_ANALYSIS` | `12` | Depth for live analysis and move grading |
| `DEPTH_FULL_ANALYSIS` | `22` | Depth for on-demand deep analysis |
| `ELO_LEVELS` | `800…3200` | The eight slider stops |
| `SOGLIA_*` | see above | Classification thresholds in centipawns |
| `EVAL_CAP` | `1000` | Evaluation bar clamp, in centipawns |
| `ANALYSIS_CACHE_SIZE` | `200` | LRU capacity for cached analyses |
| `UIColors` | dataclass | Full colour palette, including the per-label colours |

---

## Credits

- **[Stockfish](https://stockfishchess.org/)** — the analysis engine. Stockfish
  is licensed under the **GPL v3** and is deliberately **not redistributed** in
  this repository: it is downloaded and configured by the user, and this project
  merely launches it as a separate process over UCI. This keeps the MIT license
  below applicable to the code in this repository.
- **[python-chess](https://github.com/niklasf/python-chess)** by Niklas Fiekas —
  move generation, legality, SAN/UCI conversion and PGN export (GPL v3+; used as
  an external dependency, not vendored).
- **[Pygame](https://www.pygame.org/)** — rendering and input.
- **Piece sprites** (`assets/*.png`) — 68×68 greyscale+alpha PNGs, most likely
  rasterised from a standard open chess set such as the Cburnett SVG pieces
  ([Wikimedia Commons](https://commons.wikimedia.org/wiki/Category:SVG_chess_pieces),
  CC BY-SA 3.0, also shipped by [Lichess](https://github.com/lichess-org/lila/tree/master/public/piece)).
  **The files carry no embedded provenance metadata, so this attribution is
  unverified.** Before reusing this repository commercially, either confirm the
  original source and restore its exact attribution, or replace `assets/` with a
  set whose license you can cite — the loader only expects twelve PNGs named
  `{w,b}{P,N,B,R,Q,K}.png`, so any set drops in unchanged.

## License

[MIT](LICENSE) © 2026 Federico Traina
