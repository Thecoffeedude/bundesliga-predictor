# Roadmap

## Completed baseline

- **Phases 1–7 — Bundesliga platform migration:** competition abstraction,
  OpenLigaDB provider, normalized domain, caching, active payload/frontend,
  legacy isolation and validation coverage.
- **Phase 7.5 — Cross-agent documentation:** established `AGENTS.md` as the
  canonical agent guide and separated architecture, data and development docs.
- **Phase 7.6 — UI/UX refinement:** added compact grouped fixtures, responsive
  standings, desktop use, PWA install guidance and offline freshness.
- **Phase 7.7 — Visual QA / validation:** verified builds, payload rendering,
  PWA assets, boundaries and cache behavior; real-browser viewport QA remains
  documented where the preview environment was unavailable.
- **Phase 7.8 — Repository split and project cleanup:** created an independent
  Bundesliga repository baseline and removed World-Cup-only orchestration.

## Planned — not yet implemented

1. **Phase 8A — Historical Bundesliga Data Pipeline**
2. **Phase 8B — Poisson / Dixon-Coles baseline**
3. **Phase 8C — Elo**
4. **Phase 8D — ML residual second-opinion model**
5. **Phase 8E — Walk-forward evaluation/calibration**
6. **Phase 8F — Automated model retraining/update pipeline**
7. **Phase 9 — Prediction UI**
8. **Phase 10 — Season simulation**
9. **Phase 11 — Optional Kicktipp reintegration**

Phase 8A and every later item are explicitly **NOT YET IMPLEMENTED**. No model,
historical downloader, retraining pipeline or prediction UI is active.
