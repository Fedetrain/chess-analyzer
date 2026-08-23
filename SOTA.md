# SOTA — Chess Analyzer

Stato persistente della pipeline SOTA. Un solo file, tra sessioni.
Target: `public/chess-analyzer`. Avviata il **2026-08-23**.

---

## Avanzamento

```
- [x] Fase -1 Checkpoint
- [x] Fase 0 Resume check
- [x] Fase 1 Analisi
- [x] Fase 2 Ricerca
- [x] Fase 3 Roadmap
- [ ] Fase 4 Esecuzione (voce corrente: 1)
- [ ] Fase 5 Chiusura
```

---

## Analisi

*(2026-08-23, basata su lettura del codice **e su esecuzione reale**, non sul README)*

### CONCETTO
Una GUI desktop di scacchi in Pygame che fa giocare l'utente contro Stockfish
restituendo, mossa per mossa, il feedback di una board di analisi online
(barra di valutazione, freccia della mossa migliore, voto della mossa, coach testuale).

### UTENTE / USO
Giocatore amatoriale (indicativamente 800–2000 ELO) che vuole *capire* le proprie
partite mentre le gioca, non solo giocarle. Uso secondario: vetrina GitHub
professionale del suo autore.

### STATO REALE (provato eseguendo)

Ambiente di verifica: Python 3.11.9 (WindowsApps), pygame 2.6.1, python-chess 1.11.2,
`stockfish` (PyPI) **5.2.0**, binario Stockfish **17** reperito fuori dal repo e
passato via `STOCKFISH_PATH` (il repo, correttamente, non lo ridistribuisce).

**Funziona (verificato):**
- `python -m unittest test_chess_utils -v` → **5 test OK** in 1.1 s.
- La GUI si costruisce e renderizza headless (`SDL_VIDEODRIVER=dummy`):
  `Game()` → finestra 1144×720, `redraw_all()` completa un frame senza errori.
- Il layer scacchistico puro regge: mosse legali, push/pop, SAN, orientamento
  board, drag&drop e click-to-move sono corretti.
- La risoluzione del path del motore (`resolve_stockfish_path`) funziona: env var
  → `shutil.which` → `None` con messaggio di setup. Nessun path assoluto personale.

**ROTTO — P0, il difetto più grave del progetto:**
- **Il motore non parte mai con le versioni attuali della libreria.**
  `engine.py` passa `"UCI_LimitStrength": "true"` come **stringa**; il pacchetto
  `stockfish` ≥ 4 richiede un **bool**. Errore reale osservato:
  `The value for the 'UCI_LimitStrength' key has been updated from a string to a bool
  in a new release of the python stockfish package.`
  L'eccezione è catturata e degradata a `self.stockfish = None`, quindi **l'app si
  avvia in silenzio senza motore**: nessuna analisi, nessuna barra, nessuna freccia,
  e l'IA non risponde mai. Dopo `e2e4` la partita resta bloccata con l'utente che
  può muovere per entrambi i colori.
  `requirements.txt` dichiara `stockfish>=3.28.0`, cioè un range in cui il default
  di `pip install` è proprio la versione incompatibile. **Il progetto è, di fatto,
  non funzionante per chiunque lo installi oggi.**

**ROTTO — P1, verificato sperimentalmente:**
- **Barra di valutazione invertita metà delle volte.** Probe eseguito su
  Stockfish 17 + `stockfish` 5.2.0:
  - Bianco con una Donna in più, **Nero al tratto** → `{'type':'cp','value':-644}`
  - Nero con una Donna in più, **Bianco al tratto** → `{'type':'cp','value':-635}`
  Entrambi negativi: `get_evaluation()` restituisce il punteggio **dal punto di
  vista di chi muove**, non del Bianco. `drawing.draw_eval_bar()` usa il valore
  grezzo come se fosse Bianco-relativo, quindi la barra è **capovolta su ogni
  posizione con il Nero al tratto**. (`classify_move`, al contrario, la gestisce
  correttamente negando il punteggio.)
- **La barra ignora il matto.** `type: 'mate', value: 3` viene letto come 3
  centipawn: un matto in 3 disegna una barra praticamente in parità.
- **Lo slider ELO mente sotto 1320.** `set_elo` fa `max(1320, min(3190, elo))`, e il
  binario conferma il limite (`800 is below UCI_Elo's minimum value of 1320`,
  `3200 is over UCI_Elo's maximum value of 3190`). Le tacche 800 e 1200 dello slider
  producono entrambe un motore da 1320; la tacca 3200 ne produce uno da 3190.
  Le due estremità dichiarate nel README non esistono.
- `stockfish.get_parameters()` è deprecata e **solleva** `NotImplementedError` su
  5.2.0 (sostituita da `get_engine_parameters()`); il codice non la usa ancora, ma
  è il segnale che il wrapper è disallineato rispetto alla libreria.

**INCOMPLETO / DEBOLE:**
- `get_move_accuracy()` è un `return 0.0` con un commento "Placeholder".
- La classificazione usa **soglie fisse in centipawn**, metodo superato: 30 cp persi
  in una posizione pari e 30 cp persi con la Donna in più non sono lo stesso errore.
- Database aperture: **15 sequenze UCI + 16 FEN scritti a mano**, in italiano, senza
  codici ECO. Fuori da quelle righe la app dice "Apertura non comune".
- Il coach è un albero di `if` su 6 feature booleane. Spiega *la mossa*, mai *il piano*.
- Nessuna persistenza: niente storico, niente statistiche, niente profilo utente.
- Nessun sistema di studio: non esiste repertorio, drill, ripetizione spaziata.
- `MultiPV: 1` ma `get_top_moves(3)` viene chiamata comunque; il pannello ne mostra 2.
- Concorrenza fragile: `self.current_analysis` / `self.last_move_info` sono scritte da
  thread worker e lette dal main loop senza lock (mitigato, non risolto, dai
  controlli di identità FEN).
- Flag morti in `config.py`: `DIRTY_RECT_ENABLED`, `LAZY_LOADING_ENABLED`.
- Nessun `pyproject.toml`, nessun linter, nessuna CI, nessun `.env.example`.
- La UI è in italiano, il codice e i doc in inglese: incoerenza per una vetrina.

### PAROLE CHIAVE
`chess opening repertoire trainer` · `spaced repetition FSRS` · `Lichess opening
explorer API` · `ECO opening database` · `centipawn loss / win probability accuracy`
· `move classification` · `UCI engine protocol python-chess` · `chess explainability
plans` · `Maia human-like chess engine` · `PGN annotation study`

---

## Ricerca

*(svolta il **2026-08-23** — due sessioni di ricerca parallele + verifiche di rete
eseguite da questa macchina. Ogni link è stato aperto davvero; ciò che non ho
potuto confermare è marcato **NON VERIFICATO**.)*

### 2.0 — La verifica che cambia l'architettura: l'Opening Explorer di Lichess

L'utente indicava l'API `explorer.lichess.ovh` come fonte primaria del "perché".
**L'ho interrogata direttamente da questa macchina, oggi.** Risultato:

| Endpoint | Esito |
|---|---|
| `https://explorer.lichess.ovh/masters?fen=…` | **HTTP 401** (`Server: nginx`) |
| `https://explorer.lichess.ovh/lichess?fen=…` | **HTTP 401** (`Server: nginx`) |
| `https://lichess.org/api/cloud-eval?fen=…` | **HTTP 200**, JSON valido (`depth 75`) |
| `https://lichess.org/api/user/thibault` | **HTTP 200**, JSON valido |
| `https://raw.githubusercontent.com/lichess-org/chess-openings/master/a.tsv` | **HTTP 200**, 66 338 byte |
| `https://example.com` | **HTTP 200** |

La rete di questa macchina è a posto e **lichess.org risponde**: è l'host
`explorer.lichess.ovh` a rifiutare, e il 401 arriva dal suo nginx (porta gli header
CORS di Lichess, non di un proxy). Combinato con l'issue
[lila#19610 "Complete outage of explorer.lichess.ovh"](https://github.com/lichess-org/lila/issues/19610)
(aperta **2026-02-25**, che riporta 429 sistematici dopo l'incidente OVH del
2026-02-23, con conferme da En Croissant e openingtree.com), la conclusione è netta:

> **L'opening explorer di Lichess non può essere una dipendenza obbligatoria.**
> Documentato come gratuito e senza token
> ([lichess.org/api#tag/Opening-Explorer](https://lichess.org/api#tag/Opening-Explorer),
> [lila-openingexplorer](https://github.com/lichess-org/lila-openingexplorer), AGPL-3.0),
> ma **oggi non risponde**. Entra nel progetto solo come *arricchimento opzionale*
> che degrada in silenzio. Il sistema di studio deve essere **offline-first**.

Questo ribalta la premessa della richiesta ed è esattamente il motivo per cui la
skill impone di verificare ogni API con una prova, non con una citazione.

### 2.1 — Competitor (dati GitHub del 2026-08-23)

| Progetto | ★ | Ultimo push | Stack | Licenza | Cosa fa meglio |
|---|---|---|---|---|---|
| [en-croissant](https://github.com/franciscoBSalgueiro/en-croissant) | 1 801 | 2026-04-20 | Tauri/Rust/React | GPL-3.0 | Il rivale più vicino: repertorio + ripetizione spaziata + analisi + DB in un desktop |
| [maia-chess / maia3](https://github.com/CSSLab/maia-chess) | 1 225 | 2026-05-24 | Python | GPL/AGPL | Avversario *umano-simile* a un ELO scelto |
| [lichess-org/chess-openings](https://github.com/lichess-org/chess-openings) | 550 | 2026-08-04 | TSV | **CC0-1.0** | Il dataset ECO di riferimento |
| [openingtree](https://github.com/openingtree/openingtree) | 473 | 2026-05-03 | React | GPL-3.0 | *Scoperta* del repertorio dalle proprie partite |
| [listudy](https://github.com/ArneVogel/listudy) | 390 | 2026-02-24 | Elixir | AGPL-3.0 | Qualunque PGN → mazzo SRS; "blind tactics" |
| [chessdriller](https://github.com/gtim/chessdriller) | 63 | 2025-12-02 | SvelteKit | **nessuna** | Il miglior modello dati SM-2 (⚠ senza licenza: non riusabile) |

Non open source (verificato): Chessbook, ChessTempo, Chess Opening Wizard.

**Idea migliore da adottare (da chessdriller):** memorizzare il repertorio come
**archi di un grafo di posizioni** (`fen_from → fen_to`), non come nodi di un albero
di linee. Le trasposizioni collassano da sole sulla stessa carta, l'import è
idempotente, e la carta di studio ha un'unità naturale. Secondo principio: **solo le
proprie mosse sono carte**; le risposte avversarie sono lo *stimolo*.

### 2.2 — Ripetizione spaziata: FSRS-6, non SM-2

`fsrs` **6.3.2** (MIT, repo [open-spaced-repetition/py-fsrs](https://github.com/open-spaced-repetition/py-fsrs)),
pubblicato il 2026-08-09. **Verificato installandolo ed eseguendolo qui** (vedi Log):
unica dipendenza runtime `typing-extensions`, API
`Scheduler.review_card(card, Rating, now) -> (Card, ReviewLog)`,
`Rating.{Again,Hard,Good,Easy}`, e `Card.to_dict()/from_dict()` che fa round-trip
esatto — quindi la persistenza è JSON banale.
FSRS-6 (21 parametri) è lo scheduler di default di Anki da 25.09. FSRS-7 esiste solo
come ricerca nel benchmark, senza release: **da ignorare**.
**Nel mondo scacchistico quasi nessuno lo usa**: chessdriller e listudy sono ancora su
SM-2. Adottarlo è un differenziatore reale, non cosmetico.

### 2.3 — Classificazione delle mosse: probabilità di vittoria, non centipawn

Formule verificate sul sorgente primario di lila
([WinPercent.scala](https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/WinPercent.scala),
[AccuracyPercent.scala](https://raw.githubusercontent.com/lichess-org/lila/master/modules/analyse/src/main/AccuracyPercent.scala),
[Advice.scala](https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/Advice.scala))
e sulla pagina pubblica [lichess.org/page/accuracy](https://lichess.org/page/accuracy):

```
Win%      = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)          # cp limitato a ±1000
Accuracy% = 103.1668100711649 * exp(-0.04354415386753951 * ΔWin%) - 3.166924740191411 + 1
Giudizio  : ΔWin% ≥ 5 Imprecisione · ≥ 10 Errore · ≥ 15 Errore grave
```

Tre dettagli che la pagina pubblica omette e che il sorgente rivela: il **`+1` di
"uncertainty bonus"**, il **ritorno secco di 100** quando la mossa non perde Win%, e
il **clamp a [0,100]**.

**Perché è superiore alle soglie in centipawn** (il metodo attuale del progetto): la
mappa cp→Win% è una logistica, quindi la stessa perdita in centipawn vale in modo
diverso a seconda di dove ci si trova. Da 0 a −100 cp si perdono ~9 punti di Win%; da
+900 a +1000 cp se ne perde ~1. La soglia fissa "100 cp = Errore" punisce i due casi
allo stesso modo, pur avendo il secondo un impatto nullo sull'esito. La perdita in
Win% è invece **lineare nell'esito**: un punto vale lo stesso ovunque sulla scala.
Chess.com usa un Expected Points Model analogo (bande 0.02/0.05/0.10/0.20 pubblicate
[qui](https://support.chess.com/en/articles/8572705)), ma la formula CAPS2 è segreta e
**non riproducibile**: si adotta Lichess, che è verificabile.

### 2.4 — Motore: `chess.engine`, non il wrapper `stockfish`

- `stockfish` PyPI **5.2.0** (2026-04-17, [PyPI](https://pypi.org/project/stockfish/)) è
  mantenuto ma è uno shim sincrono: nessuno `stop()`, nessun `info` incrementale,
  MultiPV solo come risultato finale, solo-Stockfish, e la sua tabella di opzioni di
  default manda a Stockfish quattro parametri **che non esistono più** (`Contempt`,
  `Slow Mover`, `Minimum Thinking Time`, `Min Split Depth`).
- `chess.engine` ([docs](https://python-chess.readthedocs.io/en/latest/engine.html)) è
  già una dipendenza del progetto: `SimpleEngine.popen_uci`, `analyse(..., multipv=n)`,
  `analysis(...)` con `.stop()`, `PovScore.white()/.relative`, `Score.score(mate_score=…)`,
  `score.wdl()`. **Documentato thread-safe.**
- **`UCI_Elo` ha un minimo reale di 1320** (`spin default 1320 min 1320 max 3190`),
  confermato sia dal binario qui (`800 is below UCI_Elo's minimum value of 1320`) sia
  dal sorgente `search.h` (`LowestElo = 1320`). Sotto 1320 l'unica leva è
  **`Skill Level` 0–20** più un tetto di nodi. Lo slider 800–3200 del progetto va
  quindi reimplementato, non solo clampato.
- Stockfish stabile corrente: **18** (tag `sf_18`, 2026-01-31); qui ho testato con
  **17.1**. Il progetto non deve dipendere da una versione specifica.

### 2.5 — Le fonti del "PERCHÉ": cosa esiste davvero

Questa è la parte in cui è più facile allucinare, quindi separo netto:

**✅ Esiste ed è utilizzabile**
- **[lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)** —
  **CC0-1.0** (pubblico dominio), TSV `eco⇥name⇥pgn`, **3 810 aperture**
  (a=818 b=773 c=1251 d=615 e=358). Scaricato e verificato oggi. Dà *nome + codice ECO*.
  **È l'unica fonte di verità che si può vendorizzare senza contaminare la licenza MIT.**
- **[Wikibooks *Chess Opening Theory*](https://en.wikibooks.org/wiki/Chess_Opening_Theory)** —
  CC BY-SA 4.0, ~2 163 pagine di prosa vera sui piani. Punto chiave verificato: **l'URL
  è derivabile meccanicamente dalla sequenza di mosse**
  (`/wiki/Chess_Opening_Theory/1._e4/1...c5/2._Nf3`), quindi si può linkare la pagina
  esatta della posizione corrente senza scaricare nulla.
- **`lichess.org/api/cloud-eval`** — risponde (200 verificato), utile come fallback
  d'analisi ma non come fonte di piani.

**❌ NON esiste — e va detto invece di fingere**
> **Non esiste alcun dataset aperto, strutturato e completo di *piani* di apertura
> indicizzati per posizione.** Nessuna tabella CC0 che risponda "quali sono i piani
> tipici nella Najdorf". Tutto ciò che è completo (Chessable, ChessTempo, i libri ECO,
> i DB annotati ChessBase) è proprietario. La copertura di Wikibooks è profonda sulle
> linee principali e vuota sulle secondarie.

**Conseguenza di progetto:** il "perché" **non si scarica, si costruisce**. Tre
sorgenti che non allucinano, in cascata:
1. **Calcolo dalla posizione** — struttura pedonale, centro, spazio, pezzi bloccati.
   È matematica sulla scacchiera: sempre disponibile, sempre vera, zero rete.
2. **Base di conoscenza curata** — piani scritti a mano per le famiglie principali,
   in un JSON versionato, dichiarati come tali.
3. **Arricchimento opzionale** — explorer (quando torna), Wikibooks, LLM. Tutti
   spegnibili, tutti con fallback.

**Sugli LLM, la ricerca è un avvertimento, non un invito:** *ACT-Eval*
([arXiv 2608.04240](https://arxiv.org/abs/2608.04240), **2026-08-04**) misura che nel
commento scacchistico **GPT-5.4 senza strumenti produce sotto-affermazioni errate nel
22,0% dei casi**, e i modelli open più piccoli superano il 40%. *ChessQA*
([arXiv 2510.23948](https://arxiv.org/abs/2510.23948), 2025-10-28) trova debolezze su
tutti i livelli. Il pattern che funziona è **CCC**
([arXiv 2410.20811](https://arxiv.org/abs/2410.20811), NAACL 2025): **il motore fornisce
i concetti, l'LLM li verbalizza soltanto.** Quindi: nessun LLM come oracolo scacchistico.

**Sulla didattica, la prova che il metodo giusto funziona:** *Bridging the human–AI
knowledge gap* ([PNAS 2025-03-26, 10.1073/pnas.2406675122](https://doi.org/10.1073/pnas.2406675122),
preprint [arXiv 2310.16410](https://arxiv.org/abs/2310.16410)) ha estratto concetti da
AlphaZero filtrandoli per *insegnabilità* e *novità* e li ha trasmessi a quattro
grandi maestri, che sono **misurabilmente migliorati**. Insegnare *concetti*, non
valutazioni, è supportato dall'evidenza.

**Nota su Lichess (2026-08-12):** il suo aggiornamento semestrale annuncia motivi
tattici visuali e frecce di manovra per le linee del motore — cioè **anche Lichess
risponde al "perché" in modo grafico e deterministico, non con un LLM**. E incrocia
Stockfish con il DB master perché una mossa da maestro non venga mai bollata come
errore: idea da adottare.

### 2.6 — Tabella di confronto

| Capacità | Chess Analyzer (oggi) | en-croissant | listudy | Lichess |
|---|---|---|---|---|
| Gioco + analisi live | ⚠️ **rotto** (motore mai avviato) | ✅ | ❌ | ✅ |
| Classificazione mosse | ⚠️ soglie in centipawn | ✅ | ❌ | ✅ Win% |
| Riconoscimento aperture | ⚠️ 31 voci a mano | ✅ ECO completo | ✅ | ✅ |
| Repertorio | ❌ | ✅ | ✅ | ✅ (studies) |
| Ripetizione spaziata | ❌ | ✅ SM-2 | ✅ SM-2 | ❌ |
| **Spiegazione dei piani** | ⚠️ euristica sulla mossa | ❌ | ❌ | ⚠️ grafica |
| Offline completo | ✅ | ✅ | ❌ | ❌ |

Le due colonne dove **nessuno** è forte — *spiegazione dei piani* e *FSRS* — sono
esattamente il bersaglio.

### 2.7 — Qualità del codice (2026)

- **ruff 0.16.4** (2026-08-20) è lo standard: sostituisce black+isort+flake8+pyupgrade
  in un solo binario, configurato in `pyproject.toml` — [docs.astral.sh/ruff](https://docs.astral.sh/ruff/).
- **pytest 9.1.1** (2026-06-19).
- `pyproject.toml` è il meccanismo di dichiarazione
  ([packaging.python.org](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/));
  `requirements.txt` resta solo come artefatto pinnato.
- CI headless per pygame: `SDL_VIDEODRIVER=dummy` + `SDL_AUDIODRIVER=dummy` prima di
  `pygame.init()` — è ciò che usa la CI di pygame stessa. **Già validato qui**: il mio
  smoke test headless gira con quelle variabili.
- **pygame-ce 2.5.8** (2026-08-09) è il fork attivo; `pygame` upstream è fermo al
  **2024-09-29**. Stesso nome di import.

### Cosa NON adottare, e perché

- **L'explorer di Lichess come dipendenza obbligatoria** — non risponde (§2.0).
- **Un LLM come fonte di verità scacchistica** — 22–40% di affermazioni errate (§2.5).
- **CAPS2 di chess.com** — formula segreta, non riproducibile: si userebbe un numero
  inventato spacciato per uno standard.
- **I pesi di Maia-3** — sono **AGPL-3.0** e contaminerebbero un repo MIT; inoltre
  significherebbe PyTorch in una app Pygame. L'idea (avversario umano-simile) è
  ottima, l'integrazione è fuori scala qui.
- **Scrivere SM-2 (o peggio, un algoritmo proprio) a mano** — `fsrs` è MIT, testato e
  ha una sola dipendenza.
- **`pygame-ce`** — migrazione corretta ma non è il collo di bottiglia di questo
  progetto e rischia di rompere l'unica cosa che oggi funziona. Vedi Scartato.

---

## Roadmap

Ordinata per impatto/sforzo. Ogni voce ha un **criterio di accettazione eseguibile**.

### FONDAMENTA — far funzionare ciò che è dichiarato funzionante

- [ ] **Voce 1 — Sostituire il wrapper `stockfish` con `chess.engine`.**
  *Perché:* §2.4. Risolve in un colpo il bug P0 (motore mai avviato), la barra
  invertita (`PovScore.white()`), i matti nella barra (`score(mate_score=…)`), il
  MultiPV finto e la tabella di opzioni obsoleta. Toglie una dipendenza invece di
  aggiungerla.
  *Accettazione:* `python -m tools.selfcheck` (nuovo, headless, con `STOCKFISH_PATH`
  impostata) stampa `engine ready`, gioca 6 mosse contro il motore, e per la posizione
  "Bianco con la Donna in più, Nero al tratto" riporta una valutazione **positiva**
  per il Bianco. Senza `STOCKFISH_PATH` esce 0 dichiarando il motore assente.

- [ ] **Voce 2 — Slider di forza onesto (`Skill Level` + `UCI_Elo` + tetto nodi).**
  *Perché:* §2.4 — sotto 1320 `UCI_Elo` non esiste; oggi 800 e 1200 danno lo stesso
  motore e lo slider mente.
  *Accettazione:* un test verifica che per ogni tacca dello slider la configurazione
  prodotta sia distinta e ammessa dal binario; nessun `configure()` solleva.

- [ ] **Voce 3 — Classificazione e accuratezza in probabilità di vittoria.**
  *Perché:* §2.3.
  *Accettazione:* `pytest tests/test_accuracy.py` verde, con casi che riproducono i
  valori pubblicati di Lichess (Win% a 0 cp = 50; mossa che non perde Win% = 100%;
  soglie 5/10/15) e un test che dimostra la proprietà chiave: 100 cp persi in parità
  producono un giudizio peggiore di 100 cp persi da +900.

- [ ] **Voce 4 — Database ECO completo (CC0) al posto delle 31 voci a mano.**
  *Perché:* §2.5. 3 810 aperture con codice ECO, pubblico dominio.
  *Accettazione:* `1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6` è riconosciuta come
  **B90 Sicilian Defense: Najdorf Variation**; la ricerca è per prefisso più lungo ed
  è tollerante alle trasposizioni.

### COLLEGAMENTI + NOVITÀ — il sistema di studio delle aperture (il cuore)

- [ ] **Voce 5 — Modello del repertorio a grafo di posizioni + import PGN.**
  *Perché:* §2.1. Archi `(colore, fen_from) → mossa`, non albero di linee: le
  trasposizioni collassano, l'import è idempotente.
  *Accettazione:* importare un PGN con due ordini di mosse che traspongono produce
  **un solo** arco per la posizione condivisa; reimportare lo stesso PGN non cambia
  il conteggio.

- [ ] **Voce 6 — Trainer con ripetizione spaziata FSRS.**
  *Perché:* §2.2 — nessun trainer scacchistico noto usa FSRS.
  *Accettazione:* un drill headless: rispondere male a una posizione la fa tornare
  prima di una risposta giusta; lo stato sopravvive a salvataggio e ricarica; con
  `fsrs` disinstallato il sistema resta usabile con uno scheduler di ripiego.

- [ ] **Voce 7 — Il PERCHÉ: motore di spiegazione dei piani.** *(la novità)*
  *Perché:* §2.5 — il dataset non esiste, quindi il "perché" si **calcola**.
  Riconoscimento della **struttura pedonale** (IQP, Carlsbad, catena francese, Maroczy,
  centro chiuso, maggioranza…) direttamente dalla scacchiera, più piani tipici per
  entrambi i colori, pezzo buono/cattivo, errori tipici e trappole della variante da
  una KB curata, più il link Wikibooks derivato dalla sequenza. Nessun competitor
  open lo fa.
  *Accettazione:* data la posizione dopo `1.d4 d5 2.c4 e6 3.Nc3 Nf6 4.cxd5 exd5` il
  sistema nomina la **struttura Carlsbad** e produce il piano corretto per entrambi i
  colori (minority attack per il Bianco), **senza rete**.

- [ ] **Voce 8 — Revisione partite: dove sei uscito dal repertorio + statistiche.**
  *Perché:* richiesta esplicita; collega classificazione, repertorio e coach.
  *Accettazione:* dato un PGN e un repertorio, il tool indica il numero di mossa
  esatto della deviazione, la mossa attesa e l'accuratezza per fase.

- [ ] **Voce 9 — Schermata Trainer in Pygame + coach ricablato sul motore dei piani.**
  *Perché:* il sistema deve essere usabile, e il coach euristico esistente non deve
  restare scollegato.
  *Accettazione:* smoke test headless che entra in modalità trainer, renderizza un
  frame, sbaglia una mossa, e verifica che compaiano confutazione e ripetizione della
  linea. **Verifica di regressione: la partita normale contro Stockfish continua a
  funzionare.**

### QUALITÀ / VETRINA

- [ ] **Voce 10 — `pyproject.toml` + ruff + pytest + CI + `.env.example` + README.**
  *Accettazione:* `ruff check .` e `ruff format --check .` puliti, `pytest -q` verde,
  workflow CI presente, nessun path assoluto personale e nessun segreto nel repo
  (verificato con grep), README aggiornato in inglese.

### Scartato (con motivo, per non riproporlo)

| Scartato | Motivo |
|---|---|
| Explorer Lichess come dipendenza obbligatoria | **HTTP 401 verificato oggi** + outage lila#19610. Resta opzionale e spegnibile. |
| Avversario Maia-3 | Pesi **AGPL-3.0** su un repo MIT + PyTorch in una app Pygame. Fuori scala. |
| LLM come generatore primario delle spiegazioni | 22–40% di affermazioni errate (ACT-Eval). Ammesso solo come verbalizzatore opzionale di concetti calcolati. |
| Migrazione a `pygame-ce` | Corretta in astratto, ma rischia l'unica parte oggi sana per zero beneficio funzionale. Annotata nel README. |
| Reimplementare CAPS2 di chess.com | Formula segreta: sarebbe un numero inventato con un nome altrui. |
| SM-2 scritto a mano | `fsrs` è MIT, testato, una sola dipendenza. |
| Self-hosting di lila-openingexplorer | AGPL + RocksDB + dump da centinaia di GB. Sproporzionato per una app desktop. |

---

## Log

- **2026-08-23 — Fase -1 Checkpoint.** Il target è un repo git pulito.
  `HEAD = 017636ce0ad806aafb75c1a020db0aa9e7f6b8cb` ("Initial commit: Chess Analyzer"),
  `git status` vuoto. Nessuna copia di backup: il commit iniziale è la rete di
  salvataggio, il rollback è `git reset --hard 017636c`.
- **2026-08-23 — Passo zero.** Verificato che l'agente precedente avesse finito:
  `README.md` presente (12,9 KB) e commit iniziale esistente. Via libera alla scrittura.
- **2026-08-23 — Fase 0.** `SOTA.md` non esisteva: pipeline avviata da zero.
- **2026-08-23 — Fase 1.** Letti tutti i 9 moduli. Eseguiti: la suite di unit test
  (5/5 OK), uno smoke test headless della GUI (frame renderizzato, mossa accettata) e
  due probe diretti sul motore. I probe hanno rivelato il bug P0 (motore mai
  inizializzato con `stockfish` 5.2.0) e il bug della barra invertita, **nessuno dei
  due documentato nel README**, che descrive entrambe le funzioni come operative.
  Conferma della regola della skill: lo stato reale ha smentito lo stato dichiarato.
- **2026-08-23 — Probe della via alternativa (`chess.engine`).** Prima di decidere la
  roadmap ho misurato l'API nativa di python-chess contro lo stesso binario.
  `SimpleEngine.popen_uci` → `id = "Stockfish 17.1"`. Risultati che decidono la
  questione:
  - `analyse(...)["score"]` è un **`PovScore`**: `.white()` e `.relative` sono due
    metodi distinti. Sulla posizione "Bianco con la Donna in più, Nero al tratto"
    restituisce `white(): +624` e `relative: -624`. **L'intera classe di bug della
    barra invertita sparisce per costruzione.**
  - `multipv=3` funziona davvero e restituisce 3 PV complete (`e2e4 +44`,
    `d2d4 +32`, `g1f3 +23`), non solo la prima mossa.
  - Opzioni UCI lette dal binario: `UCI_Elo` spin **min 1320 max 3190** (il limite è
    del motore, non del wrapper), `UCI_LimitStrength` check, **`Skill Level` spin
    0–20** — che è la leva corretta per scendere sotto 1320.
  - `score.white().score(mate_score=10000)` normalizza i matti nativamente
    (→ `9999`), rendendo superflua la normalizzazione a mano in `engine.py`.
  - `score.wdl()` restituisce direttamente **win/draw/loss** dal motore
    (`Wdl(wins=1000, draws=0, losses=0)`): è la base per un'accuratezza in
    probabilità di vittoria invece che in centipawn.
- **2026-08-23 — Probe FSRS.** `pip install --user fsrs` → **6.3.2**. Eseguito:
  `Scheduler().review_card(Card(), Rating.Again)` → richiamo a 1 minuto;
  `Good, Good, Easy` → 10 minuti, 1 giorno, 4 giorni, con `stability` che sale da
  0.212 a 3.783. `Card.from_dict(c.to_dict()) == c.to_dict()` → **True**, quindi la
  persistenza è JSON diretta. Dipendenze runtime: solo `typing-extensions`
  (torch/numpy sono extra opzionali). Adottabile senza riserve.
- **2026-08-23 — Fase 2 Ricerca.** Due sessioni di ricerca parallele più le mie
  verifiche di rete dirette. **Il risultato che ha cambiato il progetto:**
  `explorer.lichess.ovh` risponde **401** mentre `lichess.org` risponde 200 dalla
  stessa macchina — l'API su cui la richiesta dell'utente poggiava il "perché" non è
  utilizzabile oggi. Il sistema di studio è stato quindi riprogettato **offline-first**,
  con l'explorer degradato ad arricchimento opzionale. Registrata anche l'assenza
  accertata di qualunque dataset aperto di *piani* di apertura: il "perché" va
  calcolato dalla posizione, non scaricato.
- **2026-08-23 — Fase 3 Roadmap.** 10 voci, 7 scartate con motivo.
- **2026-08-23 — Nota di ambiente.** Nessun binario Stockfish è installato su `PATH`
  in questa macchina. Per i test uso quello presente nella copia originale del
  progetto (sola lettura, fuori dal target) passandolo via `STOCKFISH_PATH`. Il
  binario **non** viene copiato dentro il repo.
