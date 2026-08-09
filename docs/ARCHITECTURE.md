# Architecture

## Data flow

```text
OpenLigaDB JSON
    ↓ HTTP adapter and provider-schema validation
src/providers/openligadb.py
    ↓ Team / Fixture / Score / StandingRow
src/bundesliga_service.py
    ↓ cache, synchronization, validation, CompetitionState
src/build_bundesliga.py
    ↓ league-oriented JSON
docs/data.json
    ↓
docs/app.js + docs/index.html + docs/style.css
```

The active runtime has no API-key dependency and does not execute prediction,
odds or Kicktipp code.

## Modules

| Path | Responsibility |
|---|---|
| `config.py` | Bundesliga competition configuration and disabled feature defaults |
| `src/providers/openligadb.py` | OpenLigaDB HTTP and raw-schema boundary |
| `src/domain.py` | Immutable provider-neutral football objects |
| `src/bundesliga_service.py` | Cache, synchronization, identity registry and competition assembly |
| `src/build_bundesliga.py` | Atomic frontend payload serialization |
| `src/diagnose_openligadb.py` | Optional live schema and invariant check |
| `docs/app.js` | Matchday, standings, freshness and PWA rendering |

`src/probabilities.py` and `src/scoreline.py` are inactive reusable utilities.
They are not imported by the active builder and do not constitute Phase 8.

## Domain invariants

- `Team` uses a canonical internal ID and separately retains the OpenLigaDB ID.
- `Fixture` uses `openligadb:{MatchID}` as canonical fixture ID; kickoff is
  mutable metadata.
- Kickoffs are aware UTC timestamps. Provider-local update timestamps are
  interpreted in the competition timezone and converted to UTC.
- Full-time scores are selected by semantic result type, not list position.
- `CompetitionState` combines teams, fixtures, standings, current matchday and
  update timestamp.
- `MatchPrediction` is a reserved interface. No active code creates it.

## Provider isolation

Raw keys such as `matchID`, `team1`, `groupOrderID`, `matchResults` and
`teamInfoId` are interpreted only in the provider adapter or validation at the
cache boundary. Downstream code consumes domain objects.

## Caching

Runtime caches live under `data/cache/openligadb/` and are ignored by Git.
Entries use envelopes with `fetched_at` and `data`.

- Teams and full-season fixtures: seven-day TTL.
- Standings: fifteen-minute TTL.
- Team ID registry: persisted locally per league and season.
- Relevant matchday: refreshed only after its last-change marker changes.

Remote payloads are structurally checked before atomic replacement. Invalid or
unavailable responses cannot overwrite a valid local cache. GitHub Pages deploys
the committed `docs/data.json`; the scheduled workflow commits only that
validated deployment artifact.

## Frontend payload and PWA

The payload contains `competition`, `updated_at`, `current_matchday`,
`matchdays`, `standings`, `teams`, `features` and `source`. Each fixture carries
explicit coarse status, score and nullable `prediction` and `odds` fields. The
application never estimates a live minute.

The vanilla client exposes only `Spiele` and `Tabelle`. Fixtures are grouped by
Berlin-local kickoff slot. Phone layouts show essential table columns; wider
layouts add win/draw/loss/goals columns and desktop context. The service worker
uses network-first competition data, cache-first shell assets and cached club
crests, while marking cached payload responses for offline freshness messaging.
