# Scheduled data-branch refresh

The `Refresh dashboard data` GitHub Actions workflow is the only automated writer to the orphan `dashboard-data` branch. It runs nightly during the baseball season and remains manually runnable for recovery and historical refreshes.

## Schedule

The workflow runs daily at 09:17 UTC from March through November. The 2026 regular season is entirely in EDT, so that is 5:17 a.m. Eastern throughout the regular season. Revisit the UTC conversion before a future season. GitHub dispatches the run well after that time, between 1h28m and 2h05m late over 21–25 July 2026, for reasons that sit outside this repository; [deployment.md](deployment.md) records the measurements. The default published season comes from `config/dashboard.json`, which is changed intentionally after a new regular season begins rather than inferred from the calendar in January.

## Running it

1. Open the repository's **Actions** tab.
2. Select **Refresh dashboard data**.
3. Choose **Run workflow** from `main`.
4. Leave **Season** blank to use the configured published season, or enter a four-digit season.
5. Leave **Force rebuild** off for the normal incremental path.
6. Leave the reconciliation window at seven days unless investigating a correction.

The first run has no prior snapshot, so it requests every completed regular-season game. Later runs load `dashboard-data` and request only missing, failed, and recently completed games. Each refresh for the current calendar season also rewrites `next-games.json` and `roster-pitchers.json` from MLB's schedule and depth/40-man roster endpoints.

## Permissions and safety

The workflow has `contents: write` because it must create or update `dashboard-data`. It has no deployment, package, issue, or pull-request permissions. GitHub permits only one data refresh at a time, and queued refreshes are not cancelled halfway through.

The updater validates its in-memory snapshot before writing. A second command then reloads the serialized files, verifies manifest hashes and coverage counts, and repeats the structural validation. Only after both checks pass does the workflow create a commit and push it directly to `dashboard-data`.

A per-game MLB failure can produce a valid partial snapshot: prior data is retained as stale, while a game with no prior copy is marked missing. Structural corruption, a regressed schedule, or inconsistent manifest prevents the push entirely.

## Deployment handoff

When this workflow completes successfully, `Build and deploy dashboard` checks out the new data revision, builds the Observable site, and deploys an ephemeral Pages artifact. If refresh or validation fails, the deployment workflow skips its jobs and the last successful site stays online.

## What this workflow does not do

- It does not modify `main`.
- It does not open daily pull requests.
- It does not store raw MLB boxscores.
- It does not hold GitHub Pages deployment permissions.
- It does not commit compiled website files.
