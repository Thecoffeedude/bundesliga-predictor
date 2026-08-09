# Repository Agent Guide

## Project

This repository is the active **Bundesliga Predictor** project for the
Bundesliga 2026/27 season. The current application is a zero-key data PWA backed
by OpenLigaDB (`bl1`, season `2026`). Statistical predictions begin only in the
explicitly planned Phase 8 work and are not implemented in the baseline.

## Architecture

```text
OpenLigaDB
    ↓
src/providers/openligadb.py
    ↓ provider-neutral domain objects
src/bundesliga_service.py
    ↓ cache + CompetitionState
src/build_bundesliga.py
    ↓ docs/data.json
docs/ PWA
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Critical constraints

1. Do not fabricate predictions, odds, expected goals or live minutes.
2. Do not start a planned roadmap phase without an explicit task.
3. Do not require API keys or paid providers in the default runtime.
4. Keep OpenLigaDB fields behind the provider/normalization boundary.
5. Treat OpenLigaDB `MatchID` as provider fixture identity.
6. Treat team names and kickoff times as mutable display metadata, not identity.
7. Keep timestamps timezone-aware and normalize fixture kickoffs to UTC.
8. Preserve atomic cache writes and last-valid-cache fallback.
9. Keep `docs/data.json` as the committed GitHub Pages deployment payload.
10. Prefer focused changes over broad framework or architecture rewrites.

## Active modules

- `config.py`
- `src/domain.py`
- `src/providers/openligadb.py`
- `src/bundesliga_service.py`
- `src/build_bundesliga.py`
- `src/diagnose_openligadb.py`
- `docs/`
- `tests/test_openligadb.py`

`src/probabilities.py` and `src/scoreline.py` are retained, inactive generic
utilities. They are not connected to the Bundesliga builder. In particular,
the tested Kicktipp score optimization must not be modified or activated unless
the user explicitly scopes that work.

## Feature defaults

```text
KICKTIPP_ENABLED=false
ODDS_ENABLED=false
EXTERNAL_PREDICTIONS_ENABLED=false
```

## Commands

```bash
python3 src/build_bundesliga.py
python3 src/build_bundesliga.py --force
python3 src/diagnose_openligadb.py
python3 -m pytest -q
python3 -m pytest -q tests/test_openligadb.py
python3 -m compileall -q src
node --check docs/app.js
node --check docs/sw.js
cd docs && python3 -m http.server 8080
```

The diagnostic requires network access. Normal tests do not.

## Validation

After meaningful changes, run relevant targeted tests and the full suite. For
active-pipeline work, verify the keyless build, payload invariants, current test
count, Python compilation and frontend JavaScript syntax. Validate workflow YAML
when workflows change.

## Documentation hierarchy

- `AGENTS.md` — canonical operational guide
- `docs/ARCHITECTURE.md` — active system design
- `docs/DATA_SOURCES.md` — provider semantics
- `docs/DEVELOPMENT.md` — setup, build and validation
- `docs/ROADMAP.md` — completed and planned phases
- `README.md` — concise human-facing introduction

`CLAUDE.md` only imports this file; do not duplicate instructions there.

## Before modifying code

1. Read this file and the relevant linked documentation.
2. Inspect the existing implementation before adding abstractions.
3. Run targeted checks before and after substantial changes.
4. Validate provider assumptions against stored fixtures or the live diagnostic.
5. Report assumptions that could not be validated.
