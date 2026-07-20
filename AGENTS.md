# Agent guide

This repository is a refreshable MLB pitch-workload dashboard. Keep changes small, typed, testable, and explicit about data freshness.

## Architecture

- `app/mlb.py` owns MLB Stats API access, pacing, retries, and boxscore parsing.
- `app/db.py` owns SQLite schema and transactions.
- `app/classify.py` contains role-classification domain logic. Keep it independent from HTTP and UI code.
- `app/main.py` owns FastAPI routes and refresh orchestration.
- `frontend/src/api.ts` is the typed frontend API boundary.
- `frontend/src/hooks/useDashboard.ts` owns UI polling and refresh lifecycle.
- `frontend/src/lib/metrics.ts` contains pure presentation calculations.
- React components should primarily render typed inputs and emit user actions.

See `docs/data-model.md` and `docs/refresh-lifecycle.md` before changing storage or refresh behavior.

## Invariants

1. A team's total pitches equal both `official_sp + official_rp` and `adjusted_sp + adjusted_rp`.
2. Official SP/RP uses MLB's per-game `gamesStarted` value. Do not infer the official starter from appearance order or outing length.
3. Role-adjusted classification is conservative. A long relief outing is not automatically an SP appearance.
4. A failed refetch must never silently become current. Preserve last-known-good rows, mark the game failed, and retry it on the next incremental refresh.
5. Status must distinguish current, stale, and missing games. Do not clear a partial-refresh warning until every scheduled game is current.
6. One application worker is required while refresh locking and progress state remain in process memory.

## Validation

Run all relevant checks before committing:

```bash
python -m pytest -q
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

For backend routing or static-serving changes, also smoke-test `/`, `/health`, `/api/teams`, an unknown `/api/*` path, and one client-side route.

## Change discipline

- Add or update tests for every change to classification, refresh-state transitions, metric calculations, or polling behavior.
- Keep API response types synchronized with `frontend/src/api.ts`. If the API expands substantially, generate TypeScript types from FastAPI's OpenAPI document instead of maintaining duplicates manually.
- Use SQLite transactions for each game's data and fetch-state update.
- Do not add deployment, automatic merge, or credential-bearing workflows without explicit approval.
- Update the architecture documents when an invariant or data lifecycle changes.
