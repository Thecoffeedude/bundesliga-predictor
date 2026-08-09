# Development

## Environment

GitHub Actions runs Python 3.11. The repository does not currently declare a
formal minimum Python version. Set up the existing requirements with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The Bundesliga build requires no `.env` file and no API key.

## Build

Use fresh caches when they are within their TTLs:

```bash
python3 src/build_bundesliga.py
```

Force a full OpenLigaDB refresh:

```bash
python3 src/build_bundesliga.py --force
```

Both commands write `docs/data.json`. A normal build can fall back to the last
valid cache when OpenLigaDB is unavailable.

## Diagnostics

The optional live diagnostic requires network access and validates the current
`bl1/2026` schema and Bundesliga structural invariants:

```bash
python3 src/diagnose_openligadb.py
```

## Tests and static checks

Full offline Python suite:

```bash
python3 -m pytest -q
```

Targeted OpenLigaDB/domain/cache suite:

```bash
python3 -m pytest -q tests/test_openligadb.py
```

Frontend JavaScript syntax:

```bash
node --check docs/app.js
```

Python syntax/import compilation:

```bash
python3 -m compileall -q src
```

When workflow files change and Ruby is available, their YAML syntax can be
checked with:

```bash
ruby -e 'require "yaml"; Dir[".github/workflows/*.yml"].each { |f| YAML.parse_file(f); puts "OK #{f}" }'
```

Normal tests do not use the network. Report the test count observed in the
current run rather than treating a historical count as fixed.

## Cache

Active caches are under `data/cache/openligadb/`:

```text
teams_bl1_2026.json
fixtures_bl1_2026.json
standings_bl1_2026.json
team_registry_bl1_2026.json
last_change_bl1_2026_01.json   # number varies with relevant matchday
```

Use `--force` for normal cache regeneration. If a cache is demonstrably corrupt,
prefer moving the specific file to a backup location before rebuilding rather
than deleting the entire cache tree. Preserve `team_registry_bl1_2026.json`
unless intentionally remapping canonical club IDs.

Cache files use an envelope with `fetched_at` and `data`. Do not hand-edit them
during normal operation. This directory is machine-local and ignored by Git;
the generated deployment artifact is `docs/data.json`. A clean CI run fetches
OpenLigaDB directly and leaves the previously deployed payload unchanged if the
build fails before producing a valid replacement.

## Frontend

Build the data first, then serve the static PWA:

```bash
python3 src/build_bundesliga.py
cd docs
python3 -m http.server 8080
```

Open `http://localhost:8080`. Validate both matchday navigation and the table,
including missing/broken-logo fallbacks when frontend behavior changes.

For UI work, inspect approximately 375 px, 430 px, 768 px and 1280 px widths in
both color schemes. The `?dark` query parameter forces the dark tokens for local
inspection, and `?view=table` opens the standings view. Also verify matchday 1
and 34 boundaries, keyboard tab navigation, a failed crest request, cached data
while offline and the deliberately zeroed preseason table. Browser visual QA is
still required; syntax and parser checks are supplements rather than substitutes.

## Scheduled operation

`.github/workflows/predict.yml` is the keyless data-sync workflow. It builds and
commits only the deployable `docs/data.json` payload; runtime caches remain
machine-local.
