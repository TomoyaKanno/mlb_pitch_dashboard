# MLB Pitch Workload Dashboard

A self-contained dashboard that calculates team pitch workloads directly from the public MLB Stats API, stores game-level results in SQLite, and exposes both official appearance and role-adjusted SP/RP views.

## Quick start

The frontend is a React + TypeScript app built with Vite; the FastAPI backend serves the built bundle. Build the frontend once, then run the backend:

```bash
# 1. Build the frontend
cd frontend
npm install
npm run build
cd ..

# 2. Run the backend (serves the built bundle at /)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>, then press **Refresh from MLB**. The first full-season refresh makes one schedule request plus one boxscore request for each completed game. Later refreshes fetch only completed games not already stored unless **Force rebuild** is selected.

### Frontend development

For hot-reload while working on the UI, run the Vite dev server alongside the backend. It proxies `/api` and `/health` to `uvicorn`, so both feel like one origin:

```bash
uvicorn app.main:app --reload          # terminal 1 (API on :8000)
cd frontend && npm run dev             # terminal 2 (UI on :5173)
```

Open the Vite URL (default <http://127.0.0.1:5173>) during development. `npm run typecheck` runs the TypeScript compiler without emitting, and `npm test` runs the frontend test suite. The Docker image builds the frontend automatically (multi-stage), so no manual build step is needed for containerized runs.

The status line reports the exact API-call count for each refresh.

### Request pacing and resilience

Outbound requests to the MLB API are both concurrency-capped and rate-limited. The concurrency cap bounds how many boxscore requests are in flight; the rate limit paces how fast new requests may start, so a small pool cannot burst hundreds of requests per second when responses come back quickly. Throttled (`429`) and server (`5xx`) responses are retried with jittered exponential backoff, honoring a numeric `Retry-After` header when the server sends one.

A single game whose request exhausts its retries no longer aborts the whole refresh. The remaining games are stored and classified, while the failed game is marked retryable. Last-known-good data is retained as stale; a game with no cached copy is reported as missing. Either way, the next incremental refresh attempts it again.

Refreshes finish as `complete`, `partial`, or `failed`. The status line reports scheduled, current, stale, and missing coverage so a partial refresh cannot silently look complete. Failure details are available from `/api/failures`.

Tune the load with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MLB_CONCURRENCY` | `8` | Maximum in-flight requests |
| `MLB_RATE_LIMIT` | `5` | Maximum request starts per second (`0` disables pacing) |

## What the two role bases mean

**Official appearance** follows each game's `gamesStarted` flag: the first official pitcher is SP and everyone else is RP.

**Role-adjusted** preserves true starters and spot starters as SP when they work behind an opener, while keeping genuine openers in RP. The automated rules are deliberately conservative:

- An official start remains SP by default, including a short or ineffective start.
- An official reliever is moved to SP only when he throws at least 45 pitches and has another official start within 28 days.
- An official starter is moved to RP only when he throws no more than 40 pitches, is followed by a pitcher throwing at least 45, and his surrounding usage is strongly relief-dominant.
- Long relief appearances without starter evidence remain RP but are flagged for review.

Those rules avoid declaring every long reliever a starter. They cannot perfectly identify an MLB debut or one-off bulk appearance whose starter evidence exists only in MiLB, so every reclassification and ambiguous long outing is exposed by `/api/audit`.

## Manual overrides

Edit `config/role_overrides.json` for known edge cases:

```json
{
  "823925:660271": {
    "role": "SP",
    "note": "Scheduled bulk starter behind an opener"
  }
}
```

The key is `gamePk:playerId`. Valid roles are `SP` and `RP`. Overrides are applied during the next refresh/reclassification pass.

## API endpoints

- `POST /api/refresh` — start an incremental or forced refresh
- `GET /api/status` — progress, API calls, and last-refresh metadata
- `GET /api/teams` — all 30 team aggregates
- `GET /api/audit` — reclassified and review-flagged appearances
- `GET /api/failures` — retryable game failures and stale-cache state
- `GET /health` — basic health check

Example refresh body:

```json
{
  "season": 2026,
  "force": false
}
```

## Docker

```bash
docker build -t mlb-pitch-dashboard .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" mlb-pitch-dashboard
```

Run one application worker so the in-process refresh lock and progress state remain authoritative. SQLite data lives at `data/mlb.sqlite3` locally or `/data/mlb.sqlite3` in the container.

## Continuous integration

GitHub Actions runs the Python tests plus the frontend type-check, tests, and production build on every pull request and every push to `main`. It has read-only repository access and does not deploy or merge code. See [`docs/continuous-integration.md`](docs/continuous-integration.md) for what each check does and how it differs from local validation.

## Data and usage note

This is an unofficial personal project. MLB endpoints and response shapes can change without notice. Use a reasonable refresh cadence and review MLB's applicable terms before publishing or commercializing a deployment.
