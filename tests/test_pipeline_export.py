from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.export import (
    aggregate_complete_games,
    aggregate_bullpen_usage,
    aggregate_recent_games,
    aggregate_team_timeseries,
    aggregate_teams,
    export_dashboard,
    export_team_timeseries,
    reconcile_team_timeseries,
)
from pipeline.schema import AppearanceRecord, FetchStateRecord, GameRecord, Snapshot
from pipeline.storage import write_snapshot


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc).isoformat()


def _write_two_day_snapshot(tmp_path) -> None:
    snapshot = Snapshot(season=2026)
    for game_pk, game_date in ((1, "2026-07-18"), (2, "2026-07-19")):
        snapshot.games[game_pk] = GameRecord(game_pk, game_date, 2026, "Final")
        snapshot.fetch_state[game_pk] = FetchStateRecord(
            game_pk, "success", NOW, NOW, None, 1,
        )

    rows = [
        AppearanceRecord(
            1, "2026-07-18", 2026, 100, "Away", 11, "Starter", 80,
            True, 0, "SP", "official starter",
        ),
        AppearanceRecord(
            1, "2026-07-18", 2026, 100, "Away", 12, "Reliever", 20,
            False, 1, "RP", "official reliever",
        ),
        AppearanceRecord(
            1, "2026-07-18", 2026, 200, "Home", 21, "Starter", 90,
            True, 0, "SP", "official starter",
        ),
        AppearanceRecord(
            1, "2026-07-18", 2026, 200, "Home", 22, "Reliever", 15,
            False, 1, "RP", "official reliever",
        ),
        AppearanceRecord(
            2, "2026-07-19", 2026, 100, "Away", 11, "Starter", 30,
            True, 0, "RP", "relief-dominant opener",
        ),
        AppearanceRecord(
            2, "2026-07-19", 2026, 100, "Away", 12, "Bulk", 70,
            False, 1, "SP", "starter-identity bulk appearance",
        ),
        AppearanceRecord(
            2, "2026-07-19", 2026, 200, "Home", 21, "Starter", 95,
            True, 0, "SP", "official starter",
        ),
        AppearanceRecord(
            2, "2026-07-19", 2026, 200, "Home", 22, "Reliever", 10,
            False, 1, "RP", "official reliever", needs_review=True,
        ),
    ]
    for row in rows:
        snapshot.appearances[row.key] = row

    refresh = {
        "result": "complete",
        "generated_at": NOW,
        "api_calls": 2,
        "scheduled_games": 2,
        "games_requested": 2,
        "games_fetched": 2,
        "games_failed": 0,
        "current_games": 2,
        "stale_games": 0,
        "missing_games": 0,
    }
    write_snapshot(snapshot, refresh, tmp_path)


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


def test_team_timeseries_daily_increments_reconcile_to_season_totals(tmp_path):
    _write_two_day_snapshot(tmp_path)

    dashboard = export_dashboard(tmp_path, 2026)
    series = export_team_timeseries(tmp_path, 2026)

    assert series["schema_version"] == 1
    assert series["season"] == 2026
    assert series["status"]["current_games"] == 2
    assert [point["date"] for point in series["points"][:2]] == ["2026-07-18", "2026-07-18"]

    away_days = [point for point in series["points"] if point["team_id"] == 100]
    assert len(away_days) == 2
    assert away_days[0]["total"] == 100
    assert away_days[1]["total"] == 100
    assert away_days[1]["bulk_to_sp"] == 70
    assert away_days[1]["opener_to_rp"] == 30

    reconcile_team_timeseries(dashboard["teams"], series["points"])
    assert series["complete_games"] == []


def test_complete_games_are_game_grain_so_doubleheaders_keep_cgs():
    """A CG + bullpen game the same day must not hide the CG in day totals."""
    snapshot = Snapshot(season=2026)
    # Game 10: true CG (no RP).
    snapshot.appearances[(10, 119, 607192)] = AppearanceRecord(
        10, "2026-07-19", 2026, 119, "Los Angeles Dodgers", 607192, "Yoshinobu Yamamoto",
        108, True, 0, "SP", "official starter",
    )
    # Game 11: same date, bullpen used — day total will show official_rp > 0.
    snapshot.appearances[(11, 119, 607192)] = AppearanceRecord(
        11, "2026-07-19", 2026, 119, "Los Angeles Dodgers", 607192, "Yoshinobu Yamamoto",
        70, True, 0, "SP", "official starter",
    )
    snapshot.appearances[(11, 119, 608331)] = AppearanceRecord(
        11, "2026-07-19", 2026, 119, "Los Angeles Dodgers", 608331, "Reliever",
        30, False, 1, "RP", "official reliever",
    )

    points = aggregate_team_timeseries(snapshot)
    day = next(point for point in points if point["team_id"] == 119)
    assert day["date"] == "2026-07-19"
    assert day["games"] == 2
    assert day["official_rp"] == 30
    assert day["official_sp"] == 178

    complete = aggregate_complete_games(snapshot)
    assert complete == [
        {
            "date": "2026-07-19",
            "game_pk": 10,
            "team_id": 119,
            "team_name": "Los Angeles Dodgers",
            "pitches": 108,
            "pitcher_id": 607192,
            "pitcher_name": "Yoshinobu Yamamoto",
        }
    ]


def test_recent_games_uses_scheduled_time_for_doubleheader_order():
    snapshot = Snapshot(season=2026)
    # The later game intentionally has the lower gamePk, so gamePk ordering would be wrong.
    snapshot.games[900] = GameRecord(900, "2026-07-20", 2026, "Final", "2026-07-20T17:10:00Z")
    snapshot.games[800] = GameRecord(800, "2026-07-20", 2026, "Final", "2026-07-20T23:10:00Z")
    snapshot.appearances[(900, 119, 1)] = AppearanceRecord(
        900, "2026-07-20", 2026, 119, "Los Angeles Dodgers", 1, "Early pitcher", 88,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(800, 119, 2)] = AppearanceRecord(
        800, "2026-07-20", 2026, 119, "Los Angeles Dodgers", 2, "Late pitcher", 94,
        True, 0, "SP", "official starter",
    )

    recent = aggregate_recent_games(snapshot)

    assert recent == [{
        "team_id": 119,
        "team_name": "Los Angeles Dodgers",
        "game_pk": 800,
        "date": "2026-07-20",
        "game_datetime": "2026-07-20T23:10:00Z",
        "pitchers": [{
            "pitcher_id": 2,
            "pitcher_name": "Late pitcher",
            "pitches": 94,
            "official_started": True,
            "appearance_order": 0,
        }],
    }]


def test_reconcile_team_timeseries_detects_drift():
    teams = [{
        "team_id": 100,
        "team_name": "Away",
        "games": 1,
        "total": 100,
        "official_sp": 60,
        "official_rp": 40,
        "adjusted_sp": 60,
        "adjusted_rp": 40,
        "bulk_to_sp": 0,
        "opener_to_rp": 0,
        "review_count": 0,
    }]
    points = [{
        "date": "2026-07-19",
        "team_id": 100,
        "team_name": "Away",
        "games": 1,
        "total": 99,
        "official_sp": 59,
        "official_rp": 40,
        "adjusted_sp": 59,
        "adjusted_rp": 40,
        "bulk_to_sp": 0,
        "opener_to_rp": 0,
        "review_count": 0,
    }]
    with pytest.raises(ValueError, match="timeseries total"):
        reconcile_team_timeseries(teams, points)


def test_fixture_team_timeseries_reconciles_with_dashboard_fixture():
    root = Path(__file__).resolve().parents[1]
    teams = json.loads((root / "observable" / "fixtures" / "dashboard.json").read_text())["teams"]
    points = json.loads(
        (root / "observable" / "fixtures" / "team-timeseries.json").read_text()
    )["points"]
    reconcile_team_timeseries(teams, points)


def test_aggregate_helpers_agree_without_persistence():
    snapshot = Snapshot(season=2026)
    snapshot.appearances[(1, 100, 11)] = AppearanceRecord(
        1, "2026-07-19", 2026, 100, "Away", 11, "Starter", 50,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(2, 100, 11)] = AppearanceRecord(
        2, "2026-07-20", 2026, 100, "Away", 11, "Starter", 40,
        True, 0, "SP", "official starter",
    )
    teams = aggregate_teams(snapshot)
    points = aggregate_team_timeseries(snapshot)
    reconcile_team_timeseries(teams, points)
    assert teams[0]["total"] == 90
    assert [point["total"] for point in points] == [50, 40]


def test_bullpen_usage_uses_fourteen_day_window_and_sums_doubleheaders() -> None:
    snapshot = Snapshot(season=2026)
    snapshot.games[900] = GameRecord(900, "2026-07-20", 2026, "Final", "2026-07-20T17:10:00Z")
    snapshot.games[800] = GameRecord(800, "2026-07-20", 2026, "Final", "2026-07-20T23:10:00Z")
    snapshot.games[700] = GameRecord(700, "2026-07-09", 2026, "Final")
    snapshot.games[600] = GameRecord(600, "2026-07-06", 2026, "Final")
    def add(game_pk: int, game_date: str, pitcher_id: int, pitcher_name: str, pitches: int, started: bool) -> None:
        snapshot.appearances[(game_pk, 17, pitcher_id)] = AppearanceRecord(
            game_pk, game_date, 2026, 17, "Test Team", pitcher_id, pitcher_name, pitches, started, 1
        )
    add(900, "2026-07-20", 1, "Starter", 80, True)
    add(900, "2026-07-20", 2, "Late Reliever", 12, False)
    add(800, "2026-07-20", 2, "Late Reliever", 18, False)
    add(700, "2026-07-09", 3, "Earlier Reliever", 25, False)
    add(600, "2026-07-06", 4, "Old Reliever", 99, False)

    usage = aggregate_bullpen_usage(snapshot)

    assert usage == [{
        "team_id": 17, "team_name": "Test Team", "end_date": "2026-07-20",
        "dates": [f"2026-07-{day:02d}" for day in range(7, 21)],
        "pitchers": [
            {"pitcher_id": 2, "pitcher_name": "Late Reliever", "pitches": [0] * 13 + [30]},
            {"pitcher_id": 3, "pitcher_name": "Earlier Reliever", "pitches": [0, 0, 25] + [0] * 11},
        ],
    }]
