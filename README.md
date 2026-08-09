# Bundesliga Predictor

A zero-key Bundesliga 2026/27 data platform and progressive web app. It uses
the free [OpenLigaDB](https://www.openligadb.de/) community API for all 34
matchdays, fixtures, results, club identities and standings.

Predictions are intentionally not implemented yet. The current baseline
provides normalized competition data, resilient local caching, a responsive
match centre and a testable interface for the later modelling phases.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/build_bundesliga.py
cd docs && python3 -m http.server 8080
```

Open `http://localhost:8080` for the responsive matchday and standings PWA.
The deployed `docs/data.json` payload remains usable through the service worker
when the network is unavailable.

Run the tests with:

```bash
python3 -m pytest -q
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data sources](docs/DATA_SOURCES.md)
- [Development and validation](docs/DEVELOPMENT.md)
- [Roadmap](docs/ROADMAP.md)
- [Coding-agent guide](AGENTS.md)

OpenLigaDB data is provided under the Open Database License (ODbL). Club image
URLs are used as returned by the provider and have frontend fallbacks.

## Provenance

This project succeeded the archived FIFA World Cup application maintained at
[`Thecoffeedude/wm2026-kicktipp`](https://github.com/Thecoffeedude/wm2026-kicktipp).
The projects have independent repositories and histories.
