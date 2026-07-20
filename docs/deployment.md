# Static dashboard deployment

The production dashboard is an Observable Framework static site deployed to GitHub Pages. The repository keeps source, durable data, and compiled output in three distinct places:

- `main` contains application and pipeline source.
- The orphan `dashboard-data` branch contains validated season snapshots.
- A short-lived GitHub Actions artifact contains the compiled site that Pages serves.

No compiled files are committed to git, and the deployed browser makes no MLB API calls.

## Automation

`Refresh dashboard data` runs every day at 5:17 a.m. in `America/New_York` from March through November. The off-hour minute avoids the busiest part of GitHub's scheduler, and the time allows late West Coast games to reach final status. It can also be run manually with an optional season, force-refresh flag, and reconciliation window.

The published season is defined once in `config/dashboard.json`. This intentional rollover guard prevents a January job from replacing the dashboard with an empty new-season snapshot. Update it after the new regular season has begun and an initial snapshot is ready.

`Build and deploy dashboard` runs in four situations:

- after a successful scheduled or manual data refresh;
- after relevant source changes reach `main`;
- when invoked manually;
- on relevant pull requests, where it builds and validates the real data but does not deploy.

The build reloads the data branch, verifies the manifest and hashes, exports browser-ready aggregates, and requires exactly 30 teams. A failed refresh does not start a production build. A failed build does not reach the deployment job, so GitHub Pages keeps serving the last successful artifact.

## One-time GitHub Pages setting

GitHub does not allow the repository's normal `GITHUB_TOKEN` to enable Pages. An administrator must do this once:

1. Open **Settings → Pages** in the repository.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. If the first post-merge deployment ran before this was enabled, open **Actions → Build and deploy dashboard** and choose **Run workflow**.

GitHub Pages sites are public even when their source repository is private. The deployed artifact therefore contains only team-level baseball aggregates and snapshot metadata, never secrets or private data.

## Failure recovery

- For an MLB or validation failure, inspect `Refresh dashboard data`; the last deployed site remains online.
- For a static build failure, inspect `Build and deploy dashboard`; no new artifact is deployed.
- For a transient job failure, rerun only the failed jobs from the Actions run.
- To rebuild without fetching MLB, manually run `Build and deploy dashboard`.
- To reconcile data manually, run `Refresh dashboard data`; a successful completion automatically starts deployment.
