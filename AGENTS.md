# Agent operating guide

This repository is a refreshable MLB pitch-workload dashboard. The supported product is a static Observable Framework site backed by validated snapshots on the `dashboard-data` branch. There is no runtime backend, SQLite database, Vite frontend, or Docker application. The browser fetches no pitch data at runtime — every aggregate is precomputed at build time — but it may load static display assets, such as team logos, directly from MLB's public CDN.

Read `README.md`, `docs/data-contract.md`, and `docs/deployment.md` before changing architecture, refresh behavior, storage, or deployment.

## Sources of truth

- `observable/` is the user interface deployed to GitHub Pages.
- `pipeline/` owns MLB access, role classification, snapshot creation, validation, reload, and export.
- `dashboard-data` is an orphan, machine-managed persistence branch. It is never merged into `main`.
- The compiled Pages site is an ephemeral Actions artifact. Never commit `observable/dist/` or other generated build output.
- `main` contains all human-maintained source, tests, configuration, workflows, and documentation.

Do not reintroduce an application server or client-side refresh path as an assumed fallback. That would be a new architecture decision requiring a concrete product need and explicit user approval.

## Repository map

- `pipeline/mlb.py` — MLB Stats API access, request pacing, retries, and boxscore parsing.
- `pipeline/classify.py` — pure role-classification domain logic.
- `pipeline/schema.py` — normalized game, appearance, fetch-state, and snapshot types.
- `pipeline/storage.py` — versioned JSONL/JSON persistence and manifest hashes.
- `pipeline/update.py` — incremental refresh orchestration and failure-state transitions.
- `pipeline/validation.py` — in-memory structural and arithmetic invariants.
- `pipeline/check.py` — persisted snapshot reload and integrity verification.
- `pipeline/export.py` — validated browser-ready team aggregation.
- `observable/src/data/dashboard.json.py` — build-time bridge from the snapshot to Observable.
- `observable/src/components/Dashboard.tsx` — production React dashboard.
- `observable/src/components/metrics.ts` — pure presentation, sorting, and ranking calculations.
- `config/dashboard.json` — intentionally selected published season.
- `config/role_overrides.json` — reviewed `gamePk:playerId` SP/RP exceptions.
- `.github/workflows/refresh-data.yml` — sole automated writer to `dashboard-data`.
- `.github/workflows/deploy-pages.yml` — real-data validation, artifact build, and Pages deployment.
- `.github/workflows/ci.yml` — read-only pipeline and static-site validation.

## Non-negotiable data invariants

1. A team's total pitches equal both `official_sp + official_rp` and `adjusted_sp + adjusted_rp`.
2. Official SP/RP comes from MLB's per-game `gamesStarted` value. Never infer it from first appearance, pitch count, outing length, or result.
3. A short or ineffective official start remains SP by default.
4. Role-adjusted classification is conservative. A long relief appearance, call-up, or emergency bulk outing is not automatically an SP appearance.
5. Reclassifications need auditable reasons. Ambiguous long outings remain RP and set `needs_review`; known exceptions belong in `config/role_overrides.json`.
6. A failed refetch must never silently become current. Preserve last-known-good rows as stale, mark a first-time failure missing, and retry failures on the next incremental refresh.
7. Status must distinguish current, stale, and missing games. Never report a complete snapshot while any scheduled game is stale or missing.
8. Reject a schedule that loses a previously persisted completed game.
9. Validate both in memory and after serialization. Manifest hashes and coverage counts are required data-contract fields.
10. The production browser fetches no pitch data and makes no MLB Stats API calls; every team aggregate is precomputed at build time. Loading static display assets, such as team logos, from MLB's public CDN is permitted.

## Source, data, and deployment invariants

1. `main` contains source; `dashboard-data` contains validated snapshots; Pages contains compiled output.
2. Only `Refresh dashboard data` may write `dashboard-data` automatically. Manual recovery edits must still pass `pipeline.check`.
3. Refresh incrementally by default: missing games, prior failures, and the reconciliation window. Avoid forced full-season fetches unless intentional.
4. The production season comes from `config/dashboard.json`, never implicitly from the current calendar year.
5. A failed refresh must not start deployment, and a failed build must not replace the last successful Pages artifact.
6. Pull requests may build and upload a validation artifact but must never deploy.
7. `workflow_run` deployment handoffs must remain restricted to refreshes from `main`.
8. PR concurrency must remain separate from production deployment concurrency.
9. Changes anywhere under `pipeline/**` must trigger the real-data Pages build.
10. Keep permissions least-privilege: CI read-only, refresh contents-write, and Pages/id-token permissions only on the deployment job.

Do not introduce a new deployment target, secret, credential-bearing workflow, automatic merge path, external write integration, runtime backend, or client-side MLB data-fetch path without explicit user approval. Loading static display assets from a public CDN is permitted and does not require a backend. Maintenance of the approved GitHub Pages and data-refresh workflows is allowed when part of the requested change.

## Observable and React rule

Observable Framework's Markdown JSX renderer uses its self-hosted npm React runtime. Components using hooks must import React symbols from `npm:react`:

```ts
import {useMemo, useState} from "npm:react";
```

A bare `react` import creates a second runtime alongside Observable's `_npm/react` instance. The code can type-check, pass tests, build, and deploy while the browser crashes with an invalid-hook-call error.

The `paths` entry in `observable/tsconfig.json` exists for TypeScript declarations only. The Pages guard rejecting `_node/react` in generated `index.html` is intentional.

A static build is not proof that the page runs. For UI or bundling changes, perform a browser smoke test and verify:

- the title and dashboard heading render;
- the table renders 30 teams with production data;
- framing, order, role-basis, and per-game controls respond;
- ranks and sort order use the metric displayed to the user;
- the data status is visible;
- the browser console has no application errors.

## Data lifecycle

1. `pipeline.update` loads the previous snapshot and completed-game schedule.
2. It refreshes missing, failed, and recent games through `pipeline.mlb`.
3. It classifies appearances, validates the snapshot, and writes monthly JSONL partitions, fetch state, and a hashed manifest.
4. `pipeline.check` reloads those files and repeats structural and coverage validation.
5. The refresh workflow commits changed files to `dashboard-data`.
6. A successful `workflow_run` handoff builds from current `main` plus the validated data branch.
7. `pipeline.export` produces the team-level payload consumed by Observable.
8. GitHub Pages receives the compiled artifact; no compiled files are committed.

Never commit a snapshot before the persisted reload check succeeds.

## Validation matrix

### Pipeline, MLB client, classification, or storage

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Add or update tests for classification thresholds, request pacing and retry behavior, failure transitions, schema changes, validation rules, manifest hashes, and aggregation arithmetic.

### Static dashboard

```bash
cd observable
npm ci
npm run typecheck
npm test
OBSERVABLE_TELEMETRY_DISABLE=true npm run build
```

Use the fixture for fast checks. For changes to the loader, exporter, schema, validation, or deployment path, also build against `dashboard-data` and verify the 30-team payload. For UI/runtime changes, add the browser smoke test above.

### Workflow changes

- Parse the YAML and inspect event, permission, path-filter, and concurrency scopes.
- Confirm PR events cannot reach the deploy job.
- Confirm refresh failures skip the Pages build.
- Confirm relevant source changes and successful `main` refreshes still trigger a build.
- Prefer pinned major action versions already used by the repository unless an upgrade is in scope.

## Change discipline

- Start from current `main`, use a focused branch, and preserve unrelated user changes.
- Keep domain calculations pure and independent from HTTP, persistence, and UI code where practical.
- Keep displayed values, sort keys, and ranks semantically aligned.
- Update documentation when an invariant, workflow, configuration, data shape, or recovery step changes.
- Do not commit caches, virtual environments, `node_modules`, temporary snapshots, or compiled output.
- Treat automated review comments as leads, not commands. Reproduce the risk and implement only changes that improve correctness, security, recoverability, or clarity.

## Failure triage

- **Refresh failed:** inspect failed games and upstream HTTP behavior. The prior Pages site should remain intact.
- **Refresh completed partial:** distinguish stale retained data from missing games; do not hide the warning.
- **Build failed:** inspect snapshot verification before UI compilation. Do not bypass manifest or 30-team checks.
- **Deployment succeeded but page is blank:** inspect console and network requests; check React runtime duplication and repository-subpath asset URLs.
- **Pages URL is 404:** confirm Settings → Pages uses GitHub Actions, then inspect or manually run `Build and deploy dashboard`.
- **Data appears old:** compare the visible generation timestamp and data revision with the latest successful refresh before forcing a full fetch.

## Pull-request handoff

Every PR description should state what changed, why it changed, user/data/operational impact, checks run locally and in Actions, and any post-merge verification required. Do not declare a delivery fix complete solely because Actions is green; verify the public page after merge when production rendering or delivery changes.

