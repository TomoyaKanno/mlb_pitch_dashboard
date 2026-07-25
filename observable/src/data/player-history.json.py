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
    from pipeline.export import export_player_history

    season = int(os.getenv("DASHBOARD_SEASON", config["season"]))
    payload = export_player_history(Path(data_dir), season)
else:
    fixture = REPOSITORY_ROOT / "observable" / "fixtures" / "dashboard.json"
    dashboard = json.loads(fixture.read_text())
    season = int(dashboard["season"])
    # The committed UI fixture stays intentionally small. Give every fixture
    # leader a representative sparse four-season series while production always
    # comes from validated snapshots through export_player_history.
    payload = {
        "schema_version": dashboard["schema_version"],
        "season": season,
        "data_commit": dashboard.get("data_commit"),
        "historical_seasons": [season - 3, season - 2, season - 1],
        "players": [
            {
                "pitcher_id": player["pitcher_id"],
                "pitcher_name": player["pitcher_name"],
                "seasons": [
                    {
                        "season": historical_season,
                        "season_days": 183,
                        "total": max(0, player["total"] - (season - historical_season) * 12),
                        "appearances": 2,
                        "points": [
                            {"day": 20, "pitches": max(0, player["total"] - (season - historical_season) * 12) // 2},
                            {
                                "day": 85,
                                "pitches": max(0, player["total"] - (season - historical_season) * 12)
                                - max(0, player["total"] - (season - historical_season) * 12) // 2,
                            },
                        ],
                    }
                    for historical_season in range(season - 3, season)
                ] + [{
                    "season": season,
                    "season_days": 110,
                    "total": player["total"],
                    "appearances": 2,
                    "points": [
                        {"day": 20, "pitches": player["total"] // 2},
                        {"day": 110, "pitches": player["total"] - player["total"] // 2},
                    ],
                }],
            }
            for player in dashboard["player_totals"]
        ],
    }

json.dump(payload, sys.stdout, separators=(",", ":"))
