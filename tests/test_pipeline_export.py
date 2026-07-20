from __future__ import annotations

from datetime import datetime, timezone

from pipeline.export import export_dashboard
from pipeline.schema import AppearanceRecord, FetchStateRecord, GameRecord, Snapshot
from pipeline.storage import write_snapshot


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc).isoformat()


def test_export_matches_runtime_team_aggregation(tmp_path):
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = GameRecord(1, "2026-07-19", 2026, "Final")
    snapshot.fetch_state[1] = FetchStateRecord(1, "success", NOW, NOW, None, 1)
    rows = [
        AppearanceRecord(
            1, "2026-07-19", 2026, 100, "Away", 11, "Starter", 30,
            True, 0, "RP", "relief-dominant opener",
        ),
        AppearanceRecord(
            1, "2026-07-19", 2026, 100, "Away", 12, "Bulk", 70,
            False, 1, "SP", "starter-identity bulk appearance",
        ),
        AppearanceRecord(
            1, "2026-07-19", 2026, 200, "Home", 21, "Starter", 90,
            True, 0, "SP", "official starter",
        ),
        AppearanceRecord(
            1, "2026-07-19", 2026, 200, "Home", 22, "Reliever", 15,
            False, 1, "RP", "official reliever",
        ),
    ]
    for row in rows:
        snapshot.appearances[row.key] = row
    refresh = {
        "result": "complete",
        "generated_at": NOW,
        "api_calls": 2,
        "scheduled_games": 1,
        "games_requested": 1,
        "games_fetched": 1,
        "games_failed": 0,
        "current_games": 1,
        "stale_games": 0,
        "missing_games": 0,
    }
    write_snapshot(snapshot, refresh, tmp_path)

    payload = export_dashboard(tmp_path, 2026)
    away = next(team for team in payload["teams"] if team["team_id"] == 100)
    assert away["games"] == 1
    assert away["total"] == 100
    assert away["official_sp"] == 30
    assert away["official_rp"] == 70
    assert away["adjusted_sp"] == 70
    assert away["adjusted_rp"] == 30
    assert away["bulk_to_sp"] == 70
    assert away["opener_to_rp"] == 30
    assert payload["status"]["current_games"] == 1
