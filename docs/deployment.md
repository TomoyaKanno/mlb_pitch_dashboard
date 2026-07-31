# Deployment and operations

Production is a static Observable Framework site on GitHub Pages. Source, durable data, and compiled output have separate owners:

- `main` contains human-maintained source and configuration.
- The orphan `dashboard-data` branch contains validated snapshots.
- A short-lived Actions artifact contains the compiled Pages site.

No compiled output is committed, and the deployed browser makes no MLB data requests.

## Workflow boundaries

| Workflow | Trigger and responsibility | Permission |
| --- | --- | --- |
| `CI` | Pull requests and pushes to `main`; Python tests plus fixture-based typecheck, tests, and build | Read-only contents |
| `Refresh dashboard data` | Scheduled or manual incremental refresh; the sole automated writer to `dashboard-data` | Contents write |
| `Build and deploy dashboard` | Real-data build after successful refreshes, relevant `main` changes, manual runs, and every pull request | Read-only build; Pages/id-token only in the deploy job |

Pull requests build and verify the real-data artifact but never deploy. The PR trigger must not be path-filtered because a skipped required workflow remains expected and can block merging. Manual refresh and deployment runs are effective only from `main`; `workflow_run` deployment handoffs accept successful refreshes from `main` only. PR and production builds use separate concurrency groups.

The build reloads the snapshot, exports the three browser payloads, compiles Observable, and runs `pipeline.verify_build`. That final verifier checks artifact identity, required team/player coverage, UI-critical payload shape, cross-payload reconciliation, and the single React runtime. Detailed domain validation stays in the pipeline and exporter tests rather than being repeated in workflow YAML.

## Schedule and season rollover

Refresh runs at 07:17 and 09:17 UTC each day from March through November. During the regular season those are 3:17 and 5:17 a.m. Eastern. Both runs use the same serialized incremental path; the early pass improves practical freshness and the later pass catches unusually late games.

GitHub schedules are best-effort. July 2026 observations placed the common two-to-three-hour delay before runner pickup, consistent with [GitHub's warning that scheduled workflows may be delayed or dropped under load](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Do not treat either cron expression as a freshness SLA or diagnose normal dispatch delay as a runner/workflow failure.

The published season is selected in `config/dashboard.json`, not inferred from the calendar. Change it only after the new regular season has begun and its initial validated snapshot is ready; this prevents an empty January rollover.

## Manual operations

### Refresh data

Open **Actions → Refresh dashboard data → Run workflow** on `main`.

- Leave **Season** blank to use `config/dashboard.json`.
- Leave **Force rebuild** off for a normal incremental refresh.
- Keep the reconciliation window at seven days unless investigating a correction.

The workflow requires an existing `dashboard-data` branch. It validates in memory, writes the snapshot, reloads and verifies hashes and coverage, then commits only when files changed. A successful refresh automatically starts a production build.

### Rebuild without fetching MLB

Run **Actions → Build and deploy dashboard → Run workflow** on `main`. This consumes the existing validated data revision.

### Verify a production-data build locally

```bash
export DASHBOARD_DATA_DIR="$PWD/../mlb-pitch-dashboard-data"
export DASHBOARD_DATA_SHA="$(git -C "$DASHBOARD_DATA_DIR" rev-parse HEAD)"
export DASHBOARD_SEASON="$(python -c 'import json; print(json.load(open("config/dashboard.json"))["season"])')"
npm --prefix observable run build
python -m pipeline.verify_build --dist-dir observable/dist
```

For UI or bundling changes, serve `observable/dist` and complete a browser smoke test covering both screens, primary controls, team/player panels, production row counts, static assets, and console errors.

## One-time Pages setting

An administrator must set **Settings → Pages → Build and deployment → Source** to **GitHub Actions**. The repository's normal `GITHUB_TOKEN` cannot enable Pages. If deployment ran before this setting was enabled, manually rerun **Build and deploy dashboard**.

Pages sites are public even when their source repository is private. The artifact may contain baseball aggregates and snapshot metadata, never secrets or private data.

## Failure recovery

- **Refresh failed:** inspect the MLB requests, failed games, and validation output. The last deployed site remains online.
- **Refresh is partial:** distinguish stale retained games from first-time missing games; the next incremental run retries both.
- **Build failed:** inspect snapshot checking, export, and compiled-payload verification. Do not bypass the manifest or coverage checks.
- **Deployment succeeded but the page is blank:** inspect browser console/network output and verify `npm:react` imports and repository-relative assets.
- **Pages returns 404:** confirm the one-time Pages setting, then rerun the build workflow.
- **Data appears old:** compare footer generation time and data revision with the latest successful refresh before forcing a full refetch.
