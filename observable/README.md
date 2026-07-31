# Observable dashboard

This directory contains the supported static UI.

```bash
npm ci
npm run dev
```

Without `DASHBOARD_DATA_DIR`, preview and builds use the committed fixture. To build a validated snapshot:

```bash
DASHBOARD_DATA_DIR=/absolute/path/to/dashboard-data npm run build
```

The published season comes from `../config/dashboard.json`; `DASHBOARD_SEASON` is an intentional override. See the repository [README](../README.md), [data contract](../docs/data-contract.md), and [deployment guide](../docs/deployment.md) for architecture and operations.
