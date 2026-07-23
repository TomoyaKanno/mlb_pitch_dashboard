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

The Python data loaders call `pipeline.export`, which reloads and validates the durable snapshot before producing browser-ready season team totals, top-30 player totals, and per-team top-five pitcher workload lists (`dashboard.json.py`), plus the team timeseries (`team-timeseries.json.py`: daily increments plus game-grain complete games). Player totals sum all season appearances by pitcher and use the current roster team when present, otherwise the latest appearance. The dashboard payload also drives the Recent strain screen (latest game, probable starter context, and roster-aware bullpen heatmap with row-aligned 3/5/14-day pitcher totals). The built site makes no MLB API calls for pitch data; the browser may load team logos and pitcher portraits from MLB's public CDN.

The default season comes from `config/dashboard.json`; `DASHBOARD_SEASON` can override it for an intentional historical build. Production automation and recovery are documented in [`docs/deployment.md`](../docs/deployment.md).
