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
| `Refresh dashboard data` | Nightly-dispatched or ad hoc incremental refresh; the sole automated writer to `dashboard-data` | Contents write |
| `Build and deploy dashboard` | Real-data build after successful refreshes, relevant `main` changes, manual runs, and every pull request | Read-only build; Pages/id-token only in the deploy job |

Pull requests build and verify the real-data artifact but never deploy. The PR trigger must not be path-filtered because a skipped required workflow remains expected and can block merging. Manual refresh and deployment runs are effective only from `main`; `workflow_run` deployment handoffs accept successful refreshes from `main` only. PR and production builds use separate concurrency groups.

The build reloads the snapshot, exports the three browser payloads, compiles Observable, and runs `pipeline.verify_build`. That final verifier checks artifact identity, required team/player coverage, UI-critical payload shape, cross-payload reconciliation, and the single React runtime. Detailed domain validation stays in the pipeline and exporter tests rather than being repeated in workflow YAML.

## Schedule and season rollover

A systemd user timer on the operator's always-on Ubuntu server dispatches `Refresh dashboard data` on `main` at 03:17 and 05:17 America/New_York from March through November. The timer runs in Eastern wall-clock time, so DST needs no adjustment. Both runs use the same serialized incremental path; the early pass improves practical freshness and the later pass catches unusually late games. GitHub cron was retired because its dispatches routinely ran two to three hours late under load, with the delay upstream of runner pickup. A dispatched run skips that schedule queue and is not subject to the inactivity auto-disable that applies to scheduled workflows.

The months are only a wake-up window; MLB's official dates decide whether a nightly run does work. The trigger sets `only_when_due`, which passes `--only-when-due` to read `regularSeasonStartDate` and `regularSeasonEndDate` from the MLB `/seasons` endpoint for the configured season. MLB moves the end date when postponed games are made up, so no calendar guess is needed. Runs before opening day skip. Every regular-season day (Eastern) refreshes. After the season, refresh continues until a `complete` snapshot has been generated on or after the end date plus the reconciliation window — the last day the final games are refetched — then skips. A missed, partial, or failed run near the end therefore catches up instead of freezing an unfinished season. Ad hoc runs leave `only_when_due` off and always refresh. A skipped run leaves `dashboard-data` unchanged, but the build still runs after it and redeploys the same data revision.

### Nightly trigger

`ops/refresh-trigger/` holds the dispatch script and the systemd service and timer. The server holds no write access: the dispatch uses a fine-grained personal access token scoped to this repository with only **Actions: Read and write**, stored outside the repository at `~/.config/mlb-refresh/token` (mode `600`). The `refresh` job's `main`-only guard keeps a token holder from running other code against `dashboard-data`. When the token is renewed, overwrite that file; nothing else changes.

Install or update as the operator user:

```bash
install -Dm755 ops/refresh-trigger/mlb-refresh-dispatch ~/.local/bin/mlb-refresh-dispatch
install -Dm644 -t ~/.config/systemd/user ops/refresh-trigger/mlb-refresh.{service,timer}
systemctl --user daemon-reload
systemctl --user enable --now mlb-refresh.timer
loginctl enable-linger "$USER"   # run without an active login session
```

`Persistent=true` fires a missed run after a reboot or outage, and the service retries for half an hour so a boot-time run survives a network that is not up yet. Inspect with `systemctl --user list-timers mlb-refresh.timer`, `journalctl --user -u mlb-refresh.service`, and `systemctl --user --failed`. While the server is down nothing refreshes; the last Pages site stays online.

The published season is selected in `config/dashboard.json`, not inferred from the calendar. Change it only after the new regular season has begun and its initial validated snapshot is ready; this prevents an empty January rollover. In practice that means after all 30 teams have completed at least one game: the build verifier requires full 30-team coverage in every dashboard section, so an international-series opening window in which only two clubs have played cannot publish yet.

## Manual operations

### Refresh data

Open **Actions → Refresh dashboard data → Run workflow** on `main`.

- Leave **Season** blank to use `config/dashboard.json`.
- Leave **Force rebuild** off for a normal incremental refresh.
- Keep the reconciliation window at seven days unless investigating a correction.
- Leave **Only when due** off; the nightly trigger sets it.

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
