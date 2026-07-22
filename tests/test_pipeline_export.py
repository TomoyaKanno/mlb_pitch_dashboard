from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.export import (
    aggregate_complete_games,
    aggregate_bullpen_usage,
    aggregate_next_games,
    aggregate_pitchers,
    aggregate_recent_games,
    aggregate_team_timeseries,
    aggregate_teams,
    export_dashboard,
    export_team_timeseries,
    reconcile_team_timeseries,
)
from pipeline.schema import (
    AppearanceRecord,
    FetchStateRecord,
    GameRecord,
    NextGameRecord,
    RosterPitcherRecord,
    Snapshot,
)
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
    snapshot.games[1] = GameRecord(
        1, "2026-07-19", 2026, "Final", "2026-07-19T23:10:00Z",
        100, "Away", 200, "Home",
    )
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
    snapshot.next_games[100] = NextGameRecord(
        100, "Away", 2, "2026-07-20", "2026-07-20T23:10:00Z",
        200, "Home", False, 11, "Away Probable",
    )
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
    assert payload["bullpen_usage"] == aggregate_bullpen_usage(snapshot)
    assert payload["next_games"] == aggregate_next_games(snapshot)
    assert payload["next_games"] == [{
        "team_id": 100,
        "team_name": "Away",
        "game_pk": 2,
        "date": "2026-07-20",
        "game_datetime": "2026-07-20T23:10:00Z",
        "opponent_id": 200,
        "opponent_name": "Home",
        "is_home": False,
        "probable_pitcher_id": 11,
        "probable_pitcher_name": "Away Probable",
        "probable_jersey_number": None,
        "probable_recent_starts": [{
            "date": "2026-07-19",
            "game_pk": 1,
            "pitches": 30,
            "opponent_name": "Home",
        }],
        "probable_days_rest": 0,
    }]


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
                "jersey_number": None,
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
    snapshot.games[900] = GameRecord(
        900, "2026-07-20", 2026, "Final", "2026-07-20T17:10:00Z"
    )
    snapshot.games[800] = GameRecord(
        800, "2026-07-20", 2026, "Final", "2026-07-20T23:10:00Z"
    )
    snapshot.games[700] = GameRecord(700, "2026-07-09", 2026, "Final")
    snapshot.games[600] = GameRecord(600, "2026-07-06", 2026, "Final")

    def add(
        game_pk: int,
        game_date: str,
        pitcher_id: int,
        pitcher_name: str,
        pitches: int,
        started: bool,
    ) -> None:
        snapshot.appearances[(game_pk, 17, pitcher_id)] = AppearanceRecord(
            game_pk,
            game_date,
            2026,
            17,
            "Test Team",
            pitcher_id,
            pitcher_name,
            pitches,
            started,
            1,
        )

    add(900, "2026-07-20", 1, "Starter", 80, True)
    add(900, "2026-07-20", 2, "Late Reliever", 12, False)
    add(800, "2026-07-20", 2, "Late Reliever", 18, False)
    add(700, "2026-07-09", 3, "Earlier Reliever", 25, False)
    add(600, "2026-07-06", 4, "Old Reliever", 99, False)

    usage = aggregate_bullpen_usage(snapshot)

    assert usage == [
        {
            "team_id": 17,
            "team_name": "Test Team",
            "end_date": "2026-07-20",
            "dates": [f"2026-07-{day:02d}" for day in range(7, 21)],
            "pitchers": [
                {
                    "pitcher_id": 2,
                    "pitcher_name": "Late Reliever",
                    "pitches": [0] * 13 + [30],
                    "depth_role": None,
                    "depth_order": None,
                    "on_depth_chart": False,
                    "availability": None,
                    "status_description": None,
                },
                {
                    "pitcher_id": 3,
                    "pitcher_name": "Earlier Reliever",
                    "pitches": [0, 0, 25] + [0] * 11,
                    "depth_role": None,
                    "depth_order": None,
                    "on_depth_chart": False,
                    "availability": None,
                    "status_description": None,
                },
            ],
        }
    ]


def test_bullpen_usage_includes_unused_depth_arms_and_roster_badges() -> None:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = GameRecord(1, "2026-07-20", 2026, "Final")
    snapshot.appearances[(1, 17, 10)] = AppearanceRecord(
        1, "2026-07-20", 2026, 17, "Test Team", 10, "Used Reliever", 20,
        False, 1, "RP", "official reliever",
    )
    snapshot.appearances[(1, 17, 11)] = AppearanceRecord(
        1, "2026-07-20", 2026, 17, "Test Team", 11, "Starter", 90,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(1, 17, 3)] = AppearanceRecord(
        1, "2026-07-20", 2026, 17, "Test Team", 3, "Injured Reliever", 14,
        False, 2, "RP", "official reliever",
    )
    snapshot.roster_pitchers[(17, 1)] = RosterPitcherRecord(
        17, "Test Team", 1, "Unused Callup", "RP", 0, "A", "Active",
    )
    snapshot.roster_pitchers[(17, 2)] = RosterPitcherRecord(
        17, "Test Team", 2, "Idle IL Reliever", "RP", 1, "D15", "Injured 15-Day",
    )
    snapshot.roster_pitchers[(17, 3)] = RosterPitcherRecord(
        17, "Test Team", 3, "Injured Reliever", "RP", 2, "D15", "Injured 15-Day",
    )
    snapshot.roster_pitchers[(17, 4)] = RosterPitcherRecord(
        17, "Test Team", 4, "Closer", "CP", 3, "A", "Active",
    )
    snapshot.roster_pitchers[(17, 10)] = RosterPitcherRecord(
        17, "Test Team", 10, "Used Reliever", "RP", 4, "RM", "Reassigned to Minors",
    )
    snapshot.roster_pitchers[(17, 99)] = RosterPitcherRecord(
        17, "Test Team", 99, "Starter Only", "SP", 5, "A", "Active",
    )

    usage = aggregate_bullpen_usage(snapshot)[0]
    assert [row["pitcher_name"] for row in usage["pitchers"]] == [
        "Unused Callup",
        "Injured Reliever",
        "Closer",
        "Used Reliever",
    ]
    assert usage["pitchers"][0]["pitches"] == [0] * 14
    assert usage["pitchers"][0]["on_depth_chart"] is True
    assert usage["pitchers"][0]["availability"] is None
    assert usage["pitchers"][1]["availability"] == "IL"
    assert usage["pitchers"][1]["pitches"][-1] == 14
    assert usage["pitchers"][2]["depth_role"] == "CP"
    assert usage["pitchers"][2]["on_depth_chart"] is True
    assert usage["pitchers"][3]["availability"] == "Minors"
    assert all(row["pitcher_name"] != "Idle IL Reliever" for row in usage["pitchers"])
    assert all(row["pitcher_id"] != 99 for row in usage["pitchers"])


def test_fixture_bullpen_usage_matches_recent_team_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "observable" / "fixtures" / "dashboard.json").read_text()
    )
    bullpen_usage = payload["bullpen_usage"]

    assert {row["team_id"] for row in bullpen_usage} == {
        row["team_id"] for row in payload["recent_games"]
    }
    for usage in bullpen_usage:
        assert len(usage["dates"]) == 14
        assert usage["dates"] == sorted(set(usage["dates"]))
        assert usage["end_date"] == usage["dates"][-1]
        for pitcher in usage["pitchers"]:
            assert len(pitcher["pitches"]) == len(usage["dates"])
            assert all(isinstance(value, int) and value >= 0 for value in pitcher["pitches"])
            assert isinstance(pitcher.get("on_depth_chart"), bool)
            assert pitcher.get("availability") is None or isinstance(pitcher["availability"], str)



def test_fixture_next_games_match_recent_team_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "observable" / "fixtures" / "dashboard.json").read_text()
    )
    next_games = payload["next_games"]

    assert {row["team_id"] for row in next_games} == {
        row["team_id"] for row in payload["recent_games"]
    }
    assert all(
        row["team_id"] != row["opponent_id"]
        and bool(row["probable_pitcher_id"] is None) == bool(row["probable_pitcher_name"] is None)
        for row in next_games
    )
    for row in next_games:
        starts = row["probable_recent_starts"]
        assert isinstance(starts, list) and len(starts) <= 3
        if row["probable_pitcher_id"] is None:
            assert starts == []
            assert row["probable_days_rest"] is None
        else:
            assert all(
                {"date", "game_pk", "pitches", "opponent_name"} <= set(start)
                and isinstance(start["pitches"], int)
                and start["pitches"] >= 0
                for start in starts
            )
            assert row["probable_days_rest"] is None or (
                isinstance(row["probable_days_rest"], int) and row["probable_days_rest"] >= 0
            )


def test_probable_starter_exports_last_three_official_starts():
    snapshot = Snapshot(season=2026)
    for game_pk, game_date, pitches in (
        (1, "2026-07-01", 80),
        (2, "2026-07-07", 95),
        (3, "2026-07-13", 101),
        (4, "2026-07-19", 88),
    ):
        snapshot.games[game_pk] = GameRecord(
            game_pk, game_date, 2026, "Final", f"{game_date}T23:10:00Z",
            100, "Away", 200, "Home",
        )
        snapshot.appearances[(game_pk, 100, 11)] = AppearanceRecord(
            game_pk, game_date, 2026, 100, "Away", 11, "Starter", pitches,
            True, 0, "SP", "official starter",
        )
    # Relief appearance must not count toward start history.
    snapshot.appearances[(4, 100, 12)] = AppearanceRecord(
        4, "2026-07-19", 2026, 100, "Away", 12, "Reliever", 20,
        False, 1, "RP", "official reliever",
    )
    snapshot.next_games[100] = NextGameRecord(
        100, "Away", 5, "2026-07-24", "2026-07-24T23:10:00Z",
        200, "Home", False, 11, "Starter",
    )
    snapshot.next_games[200] = NextGameRecord(
        200, "Home", 5, "2026-07-24", "2026-07-24T23:10:00Z",
        100, "Away", True, None, None,
    )

    rows = {row["team_id"]: row for row in aggregate_next_games(snapshot)}
    away = rows[100]
    assert away["probable_recent_starts"] == [
        {"date": "2026-07-19", "game_pk": 4, "pitches": 88, "opponent_name": "Home"},
        {"date": "2026-07-13", "game_pk": 3, "pitches": 101, "opponent_name": "Home"},
        {"date": "2026-07-07", "game_pk": 2, "pitches": 95, "opponent_name": "Home"},
    ]
    assert away["probable_days_rest"] == 4
    assert rows[200]["probable_recent_starts"] == []
    assert rows[200]["probable_days_rest"] is None


def test_player_totals_sum_all_appearances_and_label_the_current_roster_team():
    snapshot = Snapshot(season=2026)
    snapshot.appearances[(1, 100, 11)] = AppearanceRecord(
        1, "2026-07-10", 2026, 100, "Original Club", 11, "Pitcher One", 50,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(2, 200, 11)] = AppearanceRecord(
        2, "2026-07-20", 2026, 200, "Second Club", 11, "Pitcher One", 40,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(2, 200, 12)] = AppearanceRecord(
        2, "2026-07-20", 2026, 200, "Second Club", 12, "Pitcher Two", 85,
        True, 0, "SP", "official starter",
    )
    snapshot.roster_pitchers[(300, 11)] = RosterPitcherRecord(
        300, "Current Club", 11, "Pitcher One", "SP", 0, "A", "Active",
    )

    assert aggregate_pitchers(snapshot) == [
        {
            "pitcher_id": 11,
            "pitcher_name": "Pitcher One",
            "team_id": 300,
            "team_name": "Current Club",
            "total": 90,
        },
        {
            "pitcher_id": 12,
            "pitcher_name": "Pitcher Two",
            "team_id": 200,
            "team_name": "Second Club",
            "total": 85,
        },
    ]
    assert aggregate_pitchers(snapshot, limit=1)[0]["pitcher_id"] == 11
