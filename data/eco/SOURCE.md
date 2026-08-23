# ECO opening data

`a.tsv` … `e.tsv` are vendored verbatim from
**[lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)**,
retrieved **2026-08-23** from
`https://raw.githubusercontent.com/lichess-org/chess-openings/master/{a..e}.tsv`.

| File | Openings |
|---|---|
| `a.tsv` | 817 |
| `b.tsv` | 772 |
| `c.tsv` | 1250 |
| `d.tsv` | 614 |
| `e.tsv` | 357 |
| **Total** | **3810** |

**Licence: [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)**
(public domain dedication). The upstream project states: *"As a collection of
facts, this data set is in the public domain."* CC0 imposes no conditions, so
vendoring this data does not affect the MIT licence of this repository.

Format: three tab-separated columns with a header row.

```
eco	name	pgn
A00	Amar Opening	1. Nh3
A00	Amar Opening: Paris Gambit	1. Nh3 d5 2. g3 e5 3. f4
```

The data is vendored rather than fetched at runtime on purpose: opening
recognition is a core feature and must work with no network. See `SOTA.md`
(§2.0) for the measured availability problem with the Lichess opening explorer
that motivated the offline-first design.

To refresh, re-download the five files from the URL above; `openings.py` parses
them directly and needs no build step.
