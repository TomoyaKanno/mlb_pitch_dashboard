# Observable static dashboard

This is the static successor to the runtime React/FastAPI dashboard. During this migration phase the existing application remains untouched as a fallback.

```bash
cd observable
npm ci
npm run dev
```

Without environment variables, preview and CI use the small committed fixture. To build from the validated data branch checked out beside the repository source:

```bash
DASHBOARD_DATA_DIR=../dashboard-data npm run build
```

The Python data loader calls `pipeline.export`, which reloads and validates the durable snapshot before producing browser-ready team totals. The built site makes no MLB API calls and requires no runtime backend.

The default season comes from `config/dashboard.json`; `DASHBOARD_SEASON` can still override it for a local historical build. Production automation and recovery behavior are documented in [`docs/deployment.md`](../docs/deployment.md).
