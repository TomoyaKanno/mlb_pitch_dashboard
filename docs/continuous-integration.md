# Continuous integration

GitHub Actions validates the repository on fresh GitHub-hosted machines through `.github/workflows/ci.yml`.

## When it runs

- Every pull request, including drafts.
- Every push to `main`, recording the exact merged commit.

A newer run for the same branch may cancel an older one so the visible result belongs to the latest commit.

## Jobs

### Pipeline tests

1. Check out the triggering commit without retaining write credentials.
2. Install Python 3.12.
3. Cache pip downloads using the locked requirement inputs.
4. Install `requirements-dev.txt`.
5. Run `python -m pytest -q`.

These tests cover the MLB client, role classifier, incremental failure behavior, next-game persistence with optional probable starters, pitching roster persistence (depth chart / 40-man), snapshot integrity, validation invariants, season team/player export arithmetic, team pitcher-usage role framing (including swingmen), probable-starter recent-start export, roster-aware bullpen usage, and team-timeseries reconciliation.

### Static site checks

1. Install Node.js 22 and the locked Observable dependencies.
2. Run TypeScript checking.
3. Run Vitest presentation and ranking tests.
4. Build the static site from the committed fixtures (`dashboard.json` and `team-timeseries.json`).

The Python and Node jobs run independently, making the failing layer clear.

## Production-data build check

Every pull request triggers the build job in `.github/workflows/deploy-pages.yml`. This deliberate all-PR coverage keeps the required `Build validated Pages artifact` check from becoming permanently expected when a path-filtered workflow would not run. It checks out the real `dashboard-data` branch, validates the manifest, builds the proposed source against all 30 teams, verifies the season totals, top-30 player totals, one correctly ranked role-framed top-five pitcher usage record per team, latest games, populated next-game records (or the explicit legacy-empty state), probable-starter recent-start fields when announced, 14-day bullpen windows (including optional roster-aware pitcher fields), reconciled timeseries, and React runtime, and uploads a short-lived artifact. Its deployment job is skipped on pull requests.

The compiled-payload checks live in `pipeline.verify_build`, keeping the workflow itself limited to orchestration. After producing `observable/dist`, the same verifier can be run locally with `DASHBOARD_SEASON=2026 DASHBOARD_DATA_SHA=<checked-out-data-sha> python -m pipeline.verify_build --dist-dir observable/dist`.

## Security and scope

CI has read-only repository permission. It does not deploy, merge, modify branches, or use repository secrets. The Pages workflow grants deployment permissions only to its post-merge deployment job; its pull-request build remains read-only.

## Local checks versus Actions

Contributors and agents run relevant checks before committing. Actions independently verifies the committed files in a clean environment and records the result on the pull request. This catches undeclared dependencies, missing files, stale loader caches, and machine-specific assumptions.

## Optional enforcement

Branch protection can require `Pipeline tests`, `Static site checks`, and `Build validated Pages artifact` before merging. Enforcement is a repository setting, separate from the workflows.

