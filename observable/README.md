# Observable static dashboard

This directory contains the repository's supported user interface and GitHub Pages build.

```bash
npm ci
npm run dev
```

Without environment variables, preview and CI use the small committed fixture. To build from the validated data branch checked out beside the repository source:

```bash
DASHBOARD_DATA_DIR=../dashboard-data npm run build
```

The Python data loaders call `pipeline.export`, which reloads and validates the durable snapshot before producing browser-ready season team totals (`dashboard.json.py`) and the team timeseries (`team-timeseries.json.py`: daily increments plus game-grain complete games). The built site makes no MLB API calls and requires no runtime backend or database.

The default season comes from `config/dashboard.json`; `DASHBOARD_SEASON` can override it for an intentional historical build. Production automation and recovery are documented in [`docs/deployment.md`](../docs/deployment.md).

