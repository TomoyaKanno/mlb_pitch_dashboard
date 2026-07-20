from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
data_dir = os.getenv("DASHBOARD_DATA_DIR")

if data_dir:
    sys.path.insert(0, str(REPOSITORY_ROOT))
    from pipeline.export import export_dashboard

    season = int(os.getenv("DASHBOARD_SEASON", "2026"))
    payload = export_dashboard(Path(data_dir), season)
else:
    fixture = REPOSITORY_ROOT / "observable" / "fixtures" / "dashboard.json"
    payload = json.loads(fixture.read_text())

json.dump(payload, sys.stdout, separators=(",", ":"))
