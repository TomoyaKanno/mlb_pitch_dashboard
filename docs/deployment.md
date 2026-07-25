# Static dashboard deployment

The production dashboard is an Observable Framework static site deployed to GitHub Pages. The repository keeps source, durable data, and compiled output in three distinct places:

- `main` contains application and pipeline source.
- The orphan `dashboard-data` branch contains validated season snapshots.
- A short-lived GitHub Actions artifact contains the compiled site that Pages serves.

No compiled files are committed to git, and the deployed browser makes no MLB API calls.

## Automation

`Refresh dashboard data` runs every day at 09:17 UTC from March through November. During the regular season, which is entirely in EDT, that is 5:17 a.m. Eastern. Although `timezone: "America/New_York"` would express that intent more directly, the workflow deliberately uses GitHub's established UTC schedule path after the newer timezone-aware trigger repeatedly dispatched it about two hours late. Revisit the UTC conversion before a future season. The off-hour minute avoids the busiest part of GitHub's scheduler, and the time allows late West Coast games to reach final status. It can also be run manually with an optional season, force-refresh flag, and reconciliation window.

`Probe GitHub schedule latency` is a temporary read-only diagnostic scheduled for 08:17 UTC (4:17 a.m. Eastern during the 2026 regular season). It checks out no source, has no repository permissions, and records its expected time, runner start time, and calculated runner-start latency in the Actions summary. Compare its run-creation and runner-start timestamps with the 09:17 UTC production refresh, then remove the probe after enough daily samples have been collected.

The published season is defined once in `config/dashboard.json`. This intentional rollover guard prevents a January job from replacing the dashboard with an empty new-season snapshot. Update it after the new regular season has begun and an initial snapshot is ready.

`Build and deploy dashboard` runs in four situations:

- after a successful scheduled or manual data refresh;
- after relevant source changes reach `main`;
- when invoked manually;
- on every pull request, where it builds and validates the real data but does not deploy; this all-PR trigger keeps its required build check from remaining permanently expected on changes outside the prior path filter.

The build reloads the data branch, verifies the manifest and hashes, exports browser-ready aggregates (season team totals, top-30 player totals with compact current-plus-three-prior-season workload history, per-team top-five pitcher usage lists, latest-game workloads, upcoming-game records with optional probable starters and recent-start context, roster-aware 14-day bullpen windows, and the sibling team timeseries with daily points plus `complete_games`), requires exactly 30 teams, exactly 30 ranked uniquely identified player totals, matching player-history records with reconciled sparse pitch points, and one per-team pitcher-usage record with five ranked role-framed lists of at most five pitchers, and checks that recent-game, populated next-game, and bullpen team IDs match the season teams; that optional probable-starter id/name pairs are consistent; that announced probables carry well-formed `probable_recent_starts` / `probable_days_rest` fields; that bullpen pitch arrays match their 14 dates and optional roster fields are well-typed when present; and that the timeseries season/`data_commit` match the dashboard payload and reconcile to season totals. Legacy snapshots without `next-games.json` or `roster-pitchers.json` are accepted with empty/appearance-only fallbacks until the next refresh rewrites them. A failed refresh does not start a production build. A failed build does not reach the deployment job, so GitHub Pages keeps serving the last successful artifact. Compiled-payload and React-runtime checks are implemented in `pipeline.verify_build`; `.github/workflows/deploy-pages.yml` only invokes that maintained module.

## One-time GitHub Pages setting

GitHub does not allow the repository's normal `GITHUB_TOKEN` to enable Pages. An administrator must do this once:

1. Open **Settings → Pages** in the repository.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. If the first post-merge deployment ran before this was enabled, open **Actions → Build and deploy dashboard** and choose **Run workflow**.

GitHub Pages sites are public even when their source repository is private. The deployed artifact therefore contains team- and player-level baseball aggregates and snapshot metadata, never secrets or private data.

## Failure recovery

- For an MLB or validation failure, inspect `Refresh dashboard data`; the last deployed site remains online.
- For a static build failure, inspect `Build and deploy dashboard`; no new artifact is deployed.
- For a transient job failure, rerun only the failed jobs from the Actions run.
- To rebuild without fetching MLB, manually run `Build and deploy dashboard`.
- To reconcile data manually, run `Refresh dashboard data`; a successful completion automatically starts deployment.
