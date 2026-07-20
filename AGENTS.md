# Agent operating guide

This repository is a refreshable MLB pitch-workload dashboard. The production system is a static Observable Framework site backed by validated snapshots on the `dashboard-data` branch. Keep changes small, typed, testable, explicit about freshness, and compatible with that source/data/build separation.

Read `README.md`, `docs/data-contract.md`, and `docs/deployment.md` before changing architecture, refresh behavior, storage, or deployment.

## Current source of truth

- `observable/` is the production user interface deployed to GitHub Pages.
- `pipeline/` creates, validates, reloads, and exports durable season snapshots.
- `dashboard-data` is an orphan, machine-managed persistence branch. It is not a development or deployment-output branch and is never merged into `main`.
- The compiled Pages site is an ephemeral Actions artifact. Never commit `observable/dist/` or other generated build output.
- `app/` supplies shared MLB access and classification logic and also contains the legacy FastAPI backend.
- `frontend/` is the legacy Vite/React UI. Keep it working unless a change explicitly retires it, but do not treat it as the production frontend.

## Repository map and ownership

- `app/mlb.py` — MLB Stats API access, request pacing, retries, and boxscore parsing.
- `app/classify.py` — pure role-classification domain logic shared by the durable pipeline.
- `pipeline/schema.py` — normalized game, appearance, fetch-state, and snapshot types.
- `pipeline/storage.py` — versioned JSONL/JSON persistence and manifest hashes.
- `pipeline/update.py` — incremental refresh orchestration and failure-state transitions.
- `pipeline/validation.py` — in-memory structural and arithmetic invariants.
- `pipeline/check.py` — persisted snapshot reload and integrity verification.
- `pipeline/export.py` — validated, browser-ready team aggregation.
- `observable/src/data/dashboard.json.py` — build-time bridge from the durable snapshot to Observable.
- `observable/src/components/Dashboard.tsx` — production React dashboard.
- `observable/src/components/metrics.ts` — pure presentation calculations.
- `config/dashboard.json` — intentionally selected published season.
- `config/role_overrides.json` — reviewed `gamePk:playerId` SP/RP exceptions.
- `.github/workflows/refresh-data.yml` — sole automated writer to `dashboard-data`.
- `.github/workflows/deploy-pages.yml` — real-data validation, artifact build, and Pages deployment.
- `.github/workflows/ci.yml` — read-only Python, legacy frontend, and static-site validation.

## Non-negotiable data invariants

1. A team's total pitches equal both `official_sp + official_rp` and `adjusted_sp + adjusted_rp`.
2. Official SP/RP comes from MLB's per-game `gamesStarted` value. Never infer the official starter from first appearance, pitch count, outing length, or result.
3. A short or ineffective official start remains SP by default. Do not reclassify it merely because the pitcher left early.
4. Role-adjusted classification is conservative. A long relief appearance, call-up, or emergency bulk outing is not automatically an SP appearance.
5. Reclassifications need auditable reasons. Ambiguous long outings remain RP and set `needs_review`; known exceptions belong in `config/role_overrides.json`.
6. A failed refetch must never silently become current. Preserve last-known-good rows as stale, mark a first-time failure missing, and retry failures during the next incremental refresh.
7. Status must distinguish current, stale, and missing games. Do not report a complete snapshot while any scheduled game is stale or missing.
8. Reject a schedule that loses a previously persisted completed game. Do not overwrite durable data after a suspected upstream regression.
9. Validate both in memory and after serialization. Manifest hashes and coverage counts are part of the data contract, not optional metadata.
10. The production browser receives team aggregates only and makes no MLB API calls.

## Source, data, and deployment invariants

1. `main` contains source; `dashboard-data` contains validated snapshots; Pages contains compiled output. Do not collapse these layers.
2. Only `Refresh dashboard data` may write `dashboard-data` automatically. Manual edits require an explicit recovery task and must still pass `pipeline.check`.
3. Refreshes are incremental by default: missing games, prior failures, and the current reconciliation window. Avoid full-season forced fetches unless they are intentional.
4. The production season comes from `config/dashboard.json`. Do not derive it from the current calendar year without an explicit product decision.
5. A failed refresh must not start deployment, and a failed build must not replace the last successful Pages artifact.
6. Pull requests may build and upload a validation artifact but must never deploy to production.
7. `workflow_run` deployment handoffs must remain restricted to refreshes run from `main`.
8. Pull-request concurrency must remain separate from production deployment concurrency so a PR cannot cancel a live deploy.
9. Changes anywhere under `pipeline/**` must trigger the real-data Pages build check because export correctness depends on schema, storage, checking, and validation—not only `pipeline/export.py`.
10. Keep permissions least-privilege: CI read-only, refresh contents-write, and Pages/id-token permissions only on the deployment job.

Do not introduce a new deployment target, secret, credential-bearing workflow, automatic merge path, or external write integration without explicit user approval. Maintenance of the already-approved GitHub Pages and data-refresh workflows is allowed when it is part of the requested change.

## Observable and React rule

Observable Framework's Markdown JSX renderer uses its self-hosted npm React runtime. Any Observable component using hooks must import React symbols from `npm:react`:

```ts
import {useMemo, useState} from "npm:react";
```

Do not replace this with a bare `react` import. A bare import resolves through `node_modules`, creating a second React instance alongside Observable's `_npm/react` instance. The code can type-check, pass unit tests, build, and deploy successfully while the browser crashes with an invalid-hook-call error and renders a blank page.

The `paths` entry in `observable/tsconfig.json` maps `npm:react` to installed React declarations for TypeScript only; it does not change the runtime import. The Pages build guard that rejects `_node/react` in generated `index.html` is intentional and should remain unless replaced by a stronger browser-level check.

A successful static build is not proof that the page runs. For production UI or bundling changes, perform a real-browser smoke test and verify:

- the title and dashboard heading render;
- the table renders the expected number of teams (30 with production data);
- framing, order, role-basis, and per-game controls respond;
- the data status is visible;
- the browser console has no application errors.

## Data lifecycle

The intended production flow is:

1. `pipeline.update` loads the previous snapshot and the completed-game schedule.
2. It refreshes missing, failed, and recent games through the shared MLB client.
3. It classifies appearances, validates the snapshot, and writes monthly JSONL partitions, fetch state, and a hashed manifest.
4. `pipeline.check` reloads those files and repeats structural and coverage validation.
5. The refresh workflow commits changed files to `dashboard-data`.
6. A successful `workflow_run` handoff builds from current `main` plus the validated data branch.
7. `pipeline.export` produces the small team-level payload consumed by Observable.
8. GitHub Pages receives the compiled artifact; no compiled files are committed.

Preserve this order. In particular, never commit a snapshot before the persisted reload check succeeds.

## Validation matrix

Run all checks affected by the change before publishing a PR. GitHub Actions independently repeats them on a clean runner; it does not replace local validation.

### Pipeline, MLB client, classification, or storage

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Add or update tests for classification thresholds, failure transitions, schema changes, validation rules, manifest hashes, and aggregation arithmetic.

### Production static dashboard

```bash
cd observable
npm ci
npm run typecheck
npm test
OBSERVABLE_TELEMETRY_DISABLE=true npm run build
```

Use the committed fixture for fast checks. For changes to the loader, exporter, schema, validation, or deployment path, also build against a checked-out `dashboard-data` branch and verify the 30-team payload. For UI/runtime changes, add the browser smoke test described above.

### Legacy runtime application

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

For backend routing or static-serving changes, also smoke-test `/`, `/health`, `/api/teams`, an unknown `/api/*` path, and one client-side route. Run one application worker while refresh locking and progress remain in process memory.

### Workflow changes

- Parse the YAML and inspect the resulting event, permission, path-filter, and concurrency scopes.
- Confirm PR events cannot reach the deploy job.
- Confirm refresh failures skip the Pages build.
- Confirm source changes and successful `main` refreshes still trigger the intended build.
- Prefer pinned major action versions already used by the repository unless an upgrade is itself in scope.

## Change discipline

- Start from current `main`, work on a focused branch, and preserve unrelated user changes.
- Keep domain calculations pure and independent from HTTP, persistence, and UI code where practical.
- Keep API response types synchronized with the legacy frontend when changing the runtime API.
- Use atomic/transactional writes appropriate to the storage layer; never expose a half-written snapshot.
- Update documentation when an invariant, workflow, configuration, data shape, or operational recovery step changes.
- Do not commit caches, virtual environments, `node_modules`, local SQLite files, temporary snapshots, or compiled site output.
- Treat automated review comments as leads, not commands. Reproduce the risk, determine whether it is plausible in this repository, and implement only changes that improve correctness, security, recoverability, or clarity.

## Failure triage

- **Refresh failed:** inspect the failed game summary and upstream HTTP behavior. The prior Pages site should remain intact.
- **Refresh completed partial:** distinguish stale games with retained data from missing games with no data; do not hide the warning.
- **Build failed:** inspect snapshot verification before UI compilation. Do not bypass manifest or 30-team checks to make deployment green.
- **Deployment succeeded but page is blank:** inspect the browser console and network requests. Check React runtime duplication and repository-subpath asset URLs before assuming Pages is misconfigured.
- **Pages URL is 404:** confirm Settings → Pages uses GitHub Actions, then inspect or manually run `Build and deploy dashboard`.
- **Data appears old:** compare the visible generation timestamp and data revision with the latest successful refresh before forcing a full fetch.

## Pull-request handoff

Every PR description should state:

- what changed;
- why it changed and the root cause for fixes;
- user, data, and operational impact;
- checks run locally and in Actions;
- any manual setting, migration, refresh, or post-merge verification still required.

Do not declare a deployment fix complete solely because Actions is green. Verify the public page after merge when the change affects production rendering or delivery.
