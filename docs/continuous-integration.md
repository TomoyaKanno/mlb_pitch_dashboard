# Continuous integration

GitHub Actions runs the repository's validation commands on fresh GitHub-hosted machines. The main validation workflow is defined in `.github/workflows/ci.yml`.

## When it runs

- Every pull request, including drafts.
- Every push to `main`, providing a permanent check of the exact merged commit.

Opening or updating several commits quickly may cancel an older run for the same branch. This saves time and ensures the visible result belongs to the newest commit.

## Jobs

### Backend tests

1. Check out the triggering commit without retaining write credentials.
2. Install Python 3.12.
3. Cache downloaded pip packages using the requirements files as the cache key.
4. Install `requirements-dev.txt`.
5. Run `python -m pytest -q`.

### Frontend checks

1. Check out the triggering commit without retaining write credentials.
2. Install Node.js 22.
3. Cache downloaded npm packages using `package-lock.json` as the cache key.
4. Run `npm ci`, TypeScript type-checking, Vitest, and the production Vite build.

### Static site checks

1. Install the locked Observable dependencies on Node.js 22.
2. Run the static component type-check and metric tests.
3. Build the site from the small committed fixture.

These jobs run independently, so GitHub reports whether a failure belongs to Python, the fallback frontend, or the static site.

## Production-data build check

Relevant pull requests also trigger the build job in `.github/workflows/deploy-pages.yml`. It checks out the real `dashboard-data` branch, validates its manifest, builds the proposed source against all 30 teams, and uploads a short-lived artifact. The deployment job is explicitly skipped on pull requests.

## Security and scope

The CI workflow has read-only repository permission. It does not deploy the app, merge pull requests, modify branches, or use repository secrets. The Pages workflow grants deployment permissions only to its post-merge deployment job; its pull-request build remains read-only.

## Local checks versus Actions

Agents and contributors should still run relevant checks before committing. Actions independently verifies the committed files in a clean environment and records the result on the pull request. This catches missing files, undeclared dependencies, stale loader caches, and machine-specific assumptions.

## Optional enforcement

After the workflows have passed reliably, branch protection can require `Backend tests`, `Frontend checks`, `Static site checks`, and `Build validated Pages artifact` before `main` accepts a pull request. Enforcement is a repository setting and is intentionally separate from the workflows themselves.
