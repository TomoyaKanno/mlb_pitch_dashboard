# Manual data-branch refresh

The `Refresh dashboard data` GitHub Actions workflow is the only automated writer to the orphan `dashboard-data` branch. It is manual during this implementation phase; scheduling and deployment are intentionally deferred.

## Running it

1. Open the repository's **Actions** tab.
2. Select **Refresh dashboard data**.
3. Choose **Run workflow** from `main`.
4. Leave **Season** blank to use the current UTC year, or enter a four-digit season.
5. Leave **Force rebuild** off for the normal incremental path.
6. Leave the reconciliation window at seven days unless investigating a correction.

The first run has no prior snapshot, so it requests every completed regular-season game. Later runs load `dashboard-data` and request only missing, failed, and recently completed games.

## Permissions and safety

The workflow has `contents: write` because it must create or update `dashboard-data`. It has no deployment, package, issue, or pull-request permissions. GitHub permits only one data refresh at a time, and queued manual runs are not cancelled halfway through.

The updater validates its in-memory snapshot before writing. A second command then reloads the serialized files, verifies manifest hashes and coverage counts, and repeats the structural validation. Only after both checks pass does the workflow create a commit and push it directly to `dashboard-data`.

A per-game MLB failure can produce a valid partial snapshot: prior data is retained as stale, while a game with no prior copy is marked missing. Structural corruption, a regressed schedule, or inconsistent manifest prevents the push entirely.

## What this workflow does not do

- It does not modify `main`.
- It does not open daily pull requests.
- It does not store raw MLB boxscores.
- It does not build or deploy the website.
- It does not run on a schedule yet.
