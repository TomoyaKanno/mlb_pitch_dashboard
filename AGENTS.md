# Agent operating guide

This repository is a refreshable MLB pitch-workload dashboard. The supported product is a static Observable Framework site backed by validated snapshots on the `dashboard-data` branch. There is no runtime backend, SQLite database, Vite frontend, or Docker application. The browser fetches no pitch data at runtime — every aggregate is precomputed at build time — but it may load static display assets, such as team logos, directly from MLB's public CDN.

Read `README.md`, `docs/data-contract.md`, and `docs/deployment.md` before changing architecture, refresh behavior, storage, or deployment.

## ChatGPT Work mode

When operating inside ChatGPT Work mode, use the native GitHub integration for repository state, pull requests, Actions checks, and job logs. Do not fall back to the local `gh` CLI just because it is customary: it may not be installed or authenticated in that environment. This guidance is specific to ChatGPT Work mode; use the normal repository tooling in other environments.

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
- `pipeline/schema.py` — normalized game, appearance, next-game, fetch-state, and snapshot types.
- `pipeline/storage.py` — versioned JSONL/JSON persistence and manifest hashes.
- `pipeline/update.py` — incremental refresh orchestration and failure-state transitions.
- `pipeline/validation.py` — in-memory structural and arithmetic invariants.
- `pipeline/check.py` — persisted snapshot reload and integrity verification.
- `pipeline/export.py` — validated browser-ready season aggregation, latest-game and upcoming-game schedule read models, 14-day bullpen usage, and sibling team timeseries.
- `observable/src/data/dashboard.json.py` — build-time bridge from the snapshot to the season table payload.
- `observable/src/data/team-timeseries.json.py` — build-time bridge for daily team-increment series.
- `observable/src/components/Dashboard.tsx` — season-leader shell, controls, table, and timeline panel.
- `observable/src/components/RecentStrain.tsx` — latest-game workloads and 14-day bullpen heatmap.
- `observable/src/components/metrics.ts` — pure presentation, sorting, ranking, and team-series calculations.
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
import {useEffect, useMemo, useState} from "npm:react";
```

A bare `react` import creates a second runtime alongside Observable's `_npm/react` instance. The code can type-check, pass tests, build, and deploy while the browser crashes with an invalid-hook-call error.

The `paths` entry in `observable/tsconfig.json` exists for TypeScript declarations only. The Pages guard rejecting `_node/react` in generated `index.html` is intentional.

A static build is not proof that the page runs. For UI or bundling changes, perform a browser smoke test and verify:

- the title and dashboard heading render;
- the table renders 30 teams with production data;
- framing, role-basis, and per-game controls respond;
- Team and metric column headers sort ascending/descending (there is no Order dropdown);
- ranks follow the displayed metric even when rows are reordered by header sort;
- Total bars show dual-tone adjusted SP/RP fills and an MLB-average notch;
- clicking any table row opens the side timeline (Cumulative / Timecourse) with a short slide; Role adjustment disables row clicks and closes any open panel;
- the panel chart uses the shared season date axis, hover tooltip, and game-grain complete-game list with pitcher names;
- the Season leaders / Recent strain selector works; Recent strain defaults to LAD, the team picker shows pitcher names, SP/RP designation, and pitch counts from the selected team’s latest completed game, a next-game opponent with MLB’s optional probable starter (or an explicit unannounced state), and a heatmap of 14 ordered calendar days of official-reliever pitch counts;
- the panel shows the team badge and context moved out of the table column;
- snapshot diagnostics (status, coverage, generation time, API calls) appear in the footer strip below the content;
- the browser console has no application errors.

## Data lifecycle

1. `pipeline.update` loads the previous snapshot, completed-game schedule, and upcoming-game schedule records.
2. It refreshes missing, failed, and recent games through `pipeline.mlb`.
3. It classifies appearances, validates the snapshot, and writes monthly JSONL partitions, fetch state, and a hashed manifest.
4. `pipeline.check` reloads those files and repeats structural and coverage validation.
5. The refresh workflow commits changed files to `dashboard-data`.
6. A successful `workflow_run` handoff builds from current `main` plus the validated data branch.
7. `pipeline.export` produces the season team payload (including one latest completed-game pitcher list, one upcoming game with an optional probable starter, and one 14-day bullpen-usage window per team) and the sibling team timeseries (daily points plus `complete_games`); Observable renders the season leaders table, timeline panel, and Recent strain screen.
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

Use the fixture for fast checks. For changes to the loader, exporter, schema, validation, or deployment path, also build against `dashboard-data` and verify the 30-team season payload, one recent game, one upcoming game with consistent optional probable-starter fields, and one valid 14-day bullpen window per team, reconciled `team-timeseries` points, and `complete_games` list (matching season and data revision). For UI/runtime changes, add the browser smoke test above.

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

## Engineering integrity

- **No fake or partial migrations.** When you replace something, migrate the behavior, not just the appearance, and prove the new path works. A prior change left `Data source: Validated static snapshot` hardcoded in the header while the real, dynamic status lived elsewhere — the label would have kept claiming "Validated" even on a failed refresh. Snapshot diagnostics now live only in the footer strip; do not reintroduce a second, static status claim in the hero. A migration that only moves the happy-path text is not done.
- **No workarounds.** If a change appears to need a workaround, a suppressed error, a duplicated source of truth, or a "temporary" hack, stop and raise it with the user rather than shipping it. The need for a workaround is a signal that a design assumption is wrong; resolve the assumption, do not paper over it.
- **Surface concerns even when out of scope.** If you notice something that is not best practice — a latent bug, an untested path, a naming collision, a stale invariant, a smell — pause and discuss it, even if it falls outside the task you were asked to do. Drive it to a satisfying answer that becomes either a documented decision or a fix. Do not silently route around it or leave it for the next agent.
- **Prove degraded and edge states, not just the happy path.** A tone class named `warning` silently collided with Observable Framework's built-in `.warning` callout because only the complete-snapshot state was ever rendered; the bug hid until the partial state was exercised. Test or verify partial, failed, stale, empty, and error states, and prefer extracting presentation logic into pure, unit-tested helpers over asserting it only by eye.

## Failure triage

- **Refresh failed:** inspect failed games and upstream HTTP behavior. The prior Pages site should remain intact.
- **Refresh completed partial:** distinguish stale retained data from missing games; do not hide the warning.
- **Build failed:** inspect snapshot verification before UI compilation. Do not bypass manifest or 30-team checks.
- **Deployment succeeded but page is blank:** inspect console and network requests; check React runtime duplication and repository-subpath asset URLs.
- **Pages URL is 404:** confirm Settings → Pages uses GitHub Actions, then inspect or manually run `Build and deploy dashboard`.
- **Data appears old:** scroll to the footer diagnostics strip and compare the generation timestamp and data revision with the latest successful refresh before forcing a full fetch.

## Pull-request handoff

Every PR description should state what changed, why it changed, user/data/operational impact, checks run locally and in Actions, and any post-merge verification required. Do not declare a delivery fix complete solely because Actions is green; verify the public page after merge when production rendering or delivery changes.

