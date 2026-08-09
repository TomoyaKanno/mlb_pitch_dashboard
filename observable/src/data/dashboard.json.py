from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
data_dir = os.getenv("DASHBOARD_DATA_DIR")
config = json.loads((REPOSITORY_ROOT / "config" / "dashboard.json").read_text())

if data_dir:
    sys.path.insert(0, str(REPOSITORY_ROOT))
    from pipeline.classify import load_role_overrides
    from pipeline.export import export_dashboard

    season = int(os.getenv("DASHBOARD_SEASON", config["season"]))
    reviewed_through = load_role_overrides(
        REPOSITORY_ROOT / "config" / "role_overrides.json"
    ).reviewed_through
    payload = export_dashboard(
        Path(data_dir), season, role_reviewed_through=reviewed_through
    )
else:
    fixture = REPOSITORY_ROOT / "observable" / "fixtures" / "dashboard.json"
    payload = json.loads(fixture.read_text())

json.dump(payload, sys.stdout, separators=(",", ":"))
