# Continuous integration

GitHub Actions runs the repository's validation commands on a fresh GitHub-hosted machine. The workflow is defined in `.github/workflows/ci.yml`.

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

The jobs run independently, so GitHub reports whether a failure belongs to the Python or frontend side.

## Security and scope

The workflow has read-only repository permission. It does not deploy the app, merge pull requests, modify branches, or use repository secrets.

## Local checks versus Actions

Agents and contributors should still run relevant checks before committing. Actions independently verifies the committed files in a clean environment and records the result on the pull request. This catches missing files, undeclared dependencies, and machine-specific assumptions.

## Optional enforcement

After the workflow has passed reliably, branch protection can require `Backend tests` and `Frontend checks` before `main` accepts a pull request. Enforcement is a repository setting and is intentionally separate from the workflow itself.
