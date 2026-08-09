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
    aggregate_team_pitcher_usage,
    aggregate_recent_games,
    aggregate_starter_rest,
    aggregate_team_timeseries,
    aggregate_teams,
    export_dashboard,
    export_player_history,
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


def _game_record(
    game_pk: int,
    game_date: str,
    season: int = 2026,
    *,
    game_datetime: str | None = None,
) -> GameRecord:
    return GameRecord(
        game_pk, game_date, season, "Final",
        game_datetime or f"{game_date}T23:10:00Z",
        100, "Away", 200, "Home",
    )


def _write_two_day_snapshot(tmp_path) -> None:
    snapshot = Snapshot(season=2026)
    for game_pk, game_date in ((1, "2026-07-18"), (2, "2026-07-19")):
        snapshot.games[game_pk] = _game_record(game_pk, game_date)
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
        200, "Home", False, 11, "Away Probable", False, "2026-07-20",
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
    assert payload["starter_rest"] == aggregate_starter_rest(snapshot)
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
            "probable_recent_starts": [{
            "date": "2026-07-19",
            "game_pk": 1,
            "pitches": 30,
            "opponent_name": "Home",
        }],
            "probable_days_rest": 0,
            "is_rest_day_today": False,
            "schedule_date": "2026-07-20",
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
    snapshot.games[900] = GameRecord(
        900, "2026-07-20", 2026, "Final", "2026-07-20T17:10:00Z",
        119, "Los Angeles Dodgers", 137, "San Francisco Giants",
    )
    snapshot.games[800] = GameRecord(
        800, "2026-07-20", 2026, "Final", "2026-07-20T23:10:00Z",
        119, "Los Angeles Dodgers", 137, "San Francisco Giants",
    )
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
            "away_team_id": 119,
            "away_team_name": "Los Angeles Dodgers",
            "home_team_id": 137,
            "home_team_name": "San Francisco Giants",
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
    snapshot.games[900] = _game_record(
        900, "2026-07-20", game_datetime="2026-07-20T17:10:00Z",
    )
    snapshot.games[800] = _game_record(
        800, "2026-07-20", game_datetime="2026-07-20T23:10:00Z",
    )
    snapshot.games[700] = _game_record(700, "2026-07-09")
    snapshot.games[600] = _game_record(600, "2026-07-06")

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
    snapshot.games[1] = _game_record(1, "2026-07-20")
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
    snapshot.appearances[(1, 17, 5)] = AppearanceRecord(
        1, "2026-07-20", 2026, 17, "Test Team", 5, "Reserve Reliever", 12,
        False, 3, "RP", "official reliever",
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
    snapshot.roster_pitchers[(17, 5)] = RosterPitcherRecord(
        17, "Test Team", 5, "Reserve Reliever", "RP", 4, "RST", "Restricted List",
    )
    snapshot.roster_pitchers[(17, 10)] = RosterPitcherRecord(
        17, "Test Team", 10, "Used Reliever", "RP", 5, "RM", "Reassigned to Minors",
    )
    snapshot.roster_pitchers[(17, 99)] = RosterPitcherRecord(
        17, "Test Team", 99, "Starter Only", "SP", 5, "A", "Active",
    )

    usage = aggregate_bullpen_usage(snapshot)[0]
    assert [row["pitcher_name"] for row in usage["pitchers"]] == [
        "Closer",
        "Unused Callup",
        "Used Reliever",
        "Injured Reliever",
        "Reserve Reliever",
    ]
    assert usage["pitchers"][0]["depth_role"] == "CP"
    assert usage["pitchers"][0]["on_depth_chart"] is True
    assert usage["pitchers"][1]["pitches"] == [0] * 14
    assert usage["pitchers"][1]["on_depth_chart"] is True
    assert usage["pitchers"][1]["availability"] is None
    assert usage["pitchers"][2]["availability"] == "Minors"
    assert usage["pitchers"][2]["pitches"][-1] == 20
    assert usage["pitchers"][3]["availability"] == "IL"
    assert usage["pitchers"][3]["pitches"][-1] == 14
    assert usage["pitchers"][4]["availability"] == "RST"
    assert usage["pitchers"][4]["pitches"][-1] == 12
    assert all(row["pitcher_name"] != "Idle IL Reliever" for row in usage["pitchers"])
    assert all(row["pitcher_id"] != 99 for row in usage["pitchers"])


def test_bullpen_usage_marks_departed_windowed_arms_gone() -> None:
    """Windowed relievers who left the team's 40-man scope get a Gone badge.

    A waiver claim surfaces on another team's roster snapshot and names the
    new organization; an outright to a minor-league deal vanishes entirely and
    gets the generic description. Both sort below active arms.
    """
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = _game_record(1, "2026-07-20")
    for pitcher_id, pitcher_name, pitches in (
        (8, "Claimed Reliever", 53),
        (9, "Outrighted Reliever", 20),
        (10, "Active Reliever", 11),
    ):
        snapshot.appearances[(1, 17, pitcher_id)] = AppearanceRecord(
            1, "2026-07-20", 2026, 17, "Test Team", pitcher_id, pitcher_name,
            pitches, False, 1, "RP", "official reliever",
        )
    snapshot.roster_pitchers[(17, 10)] = RosterPitcherRecord(
        17, "Test Team", 10, "Active Reliever", "RP", 0, "A", "Active",
    )
    snapshot.roster_pitchers[(30, 8)] = RosterPitcherRecord(
        30, "Other Team", 8, "Claimed Reliever", None, None, "RM",
        "Reassigned to Minors",
    )

    pitchers = aggregate_bullpen_usage(snapshot)[0]["pitchers"]

    assert [row["pitcher_name"] for row in pitchers] == [
        "Active Reliever",
        "Claimed Reliever",
        "Outrighted Reliever",
    ]
    claimed, outrighted = pitchers[1], pitchers[2]
    assert claimed["availability"] == "Gone"
    assert claimed["status_description"] == "Now in the Other Team organization"
    assert claimed["on_depth_chart"] is False
    assert claimed["depth_role"] is None
    assert outrighted["availability"] == "Gone"
    assert (
        outrighted["status_description"]
        == "Not on the team's 40-man roster at the latest refresh"
    )


def test_bullpen_usage_prioritizes_latest_game_then_rolling_workload() -> None:
    snapshot = Snapshot(season=2026)
    games = (
        (1, "2026-07-20"),
        (2, "2026-07-19"),
        (3, "2026-07-18"),
        (4, "2026-07-16"),
        (5, "2026-07-12"),
        (6, "2026-07-08"),
    )
    for game_pk, game_date in games:
        snapshot.games[game_pk] = _game_record(game_pk, game_date)

    def add(
        pitcher_id: int, pitcher_name: str, game_pk: int, game_date: str, pitches: int,
    ) -> None:
        snapshot.appearances[(game_pk, 17, pitcher_id)] = AppearanceRecord(
            game_pk, game_date, 2026, 17, "Test Team", pitcher_id, pitcher_name, pitches,
            False, 1, "RP", "official reliever",
        )

    add(1, "Yesterday 10", 1, "2026-07-20", 10)
    add(2, "Yesterday 18", 1, "2026-07-20", 18)
    add(3, "Three Day Tiebreak", 3, "2026-07-18", 50)
    add(4, "Five Day Tiebreak", 3, "2026-07-18", 50)
    add(4, "Five Day Tiebreak", 4, "2026-07-16", 15)
    add(5, "Fourteen Day 40", 5, "2026-07-12", 40)
    add(6, "Fourteen Day 50", 6, "2026-07-08", 50)
    add(7, "Unavailable Yesterday", 1, "2026-07-20", 35)

    for pitcher_id, pitcher_name, depth_order, status_code in (
        (1, "Yesterday 10", 6, "A"),
        (2, "Yesterday 18", 5, "A"),
        (3, "Three Day Tiebreak", 4, "A"),
        (4, "Five Day Tiebreak", 3, "A"),
        (5, "Fourteen Day 40", 2, "A"),
        (6, "Fourteen Day 50", 1, "A"),
        (7, "Unavailable Yesterday", 0, "RM"),
    ):
        snapshot.roster_pitchers[(17, pitcher_id)] = RosterPitcherRecord(
            17, "Test Team", pitcher_id, pitcher_name, "RP", depth_order, status_code, status_code,
        )

    usage = aggregate_bullpen_usage(snapshot)[0]
    assert [row["pitcher_name"] for row in usage["pitchers"]] == [
        "Yesterday 18",
        "Yesterday 10",
        "Five Day Tiebreak",
        "Three Day Tiebreak",
        "Fourteen Day 50",
        "Fourteen Day 40",
        "Unavailable Yesterday",
    ]


def test_starter_rest_uses_active_depth_chart_and_official_start_history() -> None:
    snapshot = Snapshot(season=2026)
    for game_pk, game_date in (
        (1, "2026-07-24"),
        (2, "2026-07-25"),
        (3, "2026-07-29"),
    ):
        snapshot.games[game_pk] = _game_record(game_pk, game_date)

    # The current starter's most recent official start was for his prior team.
    snapshot.appearances[(2, 99, 1)] = AppearanceRecord(
        2, "2026-07-25", 2026, 99, "Prior Team", 1, "Traded Starter", 88,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[(1, 17, 2)] = AppearanceRecord(
        1, "2026-07-24", 2026, 17, "Current Team", 2, "Opener", 42,
        True, 0, "RP", "relief-dominant opener",
    )
    # A later role-adjusted SP relief appearance must not reset official rest.
    snapshot.appearances[(3, 17, 2)] = AppearanceRecord(
        3, "2026-07-29", 2026, 17, "Current Team", 2, "Opener", 55,
        False, 1, "SP", "starter-identity bulk appearance",
    )

    for pitcher_id, name, role, order, status in (
        (1, "Traded Starter", "SP", 5, "A"),
        (2, "Opener", "SP", 2, "A"),
        (3, "New Starter", "SP", 6, "A"),
        (4, "Injured Starter", "SP", 1, "D15"),
        (5, "Reliever", "RP", 0, "A"),
        (6, "Forty Man Only", None, None, "A"),
    ):
        snapshot.roster_pitchers[(17, pitcher_id)] = RosterPitcherRecord(
            17, "Current Team", pitcher_id, name, role, order, status, status,
        )
    snapshot.next_games[17] = NextGameRecord(
        17, "Current Team", 4, "2026-08-01", "2026-08-01T23:10:00Z",
        18, "Opponent", True, None, None,
        is_rest_day_today=False,
        schedule_date="2026-07-31",
    )

    rows = {row["team_id"]: row for row in aggregate_starter_rest(snapshot)}
    assert rows[17] == {
        "team_id": 17,
        "team_name": "Current Team",
        "as_of_date": "2026-07-31",
        "pitchers": [
            {
                "pitcher_id": 2,
                "pitcher_name": "Opener",
                "depth_role": "SP",
                "depth_order": 2,
                "status_code": "A",
                "last_start_date": "2026-07-24",
                "last_start_pitches": 42,
                "days_rest": 6,
            },
            {
                "pitcher_id": 1,
                "pitcher_name": "Traded Starter",
                "depth_role": "SP",
                "depth_order": 5,
                "status_code": "A",
                "last_start_date": "2026-07-25",
                "last_start_pitches": 88,
                "days_rest": 5,
            },
            {
                "pitcher_id": 3,
                "pitcher_name": "New Starter",
                "depth_role": "SP",
                "depth_order": 6,
                "status_code": "A",
                "last_start_date": None,
                "last_start_pitches": None,
                "days_rest": None,
            },
        ],
    }


def test_starter_rest_falls_back_to_latest_completed_game_date() -> None:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = _game_record(1, "2026-04-03")
    snapshot.appearances[(1, 17, 1)] = AppearanceRecord(
        1, "2026-04-03", 2026, 17, "Test Team", 1, "Starter", 80,
        True, 0, "SP", "official starter",
    )
    snapshot.roster_pitchers[(17, 1)] = RosterPitcherRecord(
        17, "Test Team", 1, "Starter", "SP", 0, "A", "Active",
    )

    rest = aggregate_starter_rest(snapshot)[0]
    assert rest["as_of_date"] == "2026-04-03"
    assert rest["pitchers"][0]["days_rest"] == 0


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


def test_fixture_starter_rest_matches_recent_team_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "observable" / "fixtures" / "dashboard.json").read_text()
    )
    starter_rest = payload["starter_rest"]

    assert {row["team_id"] for row in starter_rest} == {
        row["team_id"] for row in payload["recent_games"]
    }
    for rest in starter_rest:
        assert isinstance(rest["as_of_date"], str)
        assert rest["pitchers"] == sorted(
            rest["pitchers"],
            key=lambda pitcher: (
                pitcher["depth_order"], pitcher["pitcher_name"], pitcher["pitcher_id"],
            ),
        )
        for pitcher in rest["pitchers"]:
            assert pitcher["depth_role"] == "SP"
            assert pitcher["status_code"] == "A"
            if pitcher["last_start_date"] is None:
                assert pitcher["last_start_pitches"] is None
                assert pitcher["days_rest"] is None
            else:
                assert pitcher["last_start_pitches"] > 0
                assert pitcher["days_rest"] >= 0



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
        200, "Home", False, 11, "Starter", False, "2026-07-23",
    )
    snapshot.next_games[200] = NextGameRecord(
        200, "Home", 5, "2026-07-24", "2026-07-24T23:10:00Z",
        100, "Away", True, None, None, False, "2026-07-23",
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


def test_next_game_exports_snapshot_rest_day_context() -> None:
    snapshot = Snapshot(season=2026)
    snapshot.next_games[100] = NextGameRecord(
        100,
        "Resting Club",
        5,
        "2026-07-24",
        "2026-07-24T23:10:00Z",
        200,
        "Opponent",
        True,
        None,
        None,
        is_rest_day_today=True,
        schedule_date="2026-07-23",
    )

    assert aggregate_next_games(snapshot) == [{
        "team_id": 100,
        "team_name": "Resting Club",
        "game_pk": 5,
        "date": "2026-07-24",
        "game_datetime": "2026-07-24T23:10:00Z",
        "opponent_id": 200,
        "opponent_name": "Opponent",
        "is_home": True,
        "probable_pitcher_id": None,
        "probable_pitcher_name": None,
        "probable_recent_starts": [],
        "probable_days_rest": None,
        "is_rest_day_today": True,
        "schedule_date": "2026-07-23",
    }]


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


def test_player_history_exports_sparse_prior_season_points_and_zero_mlb_history(tmp_path):
    def write_season(
        season: int,
        first_pitcher: tuple[int, str, int],
        last_pitcher: tuple[int, str, int],
        *,
        stale_second_game: bool = False,
    ) -> None:
        snapshot = Snapshot(season=season)
        game_rows = (
            (season * 10 + 1, f"{season}-03-30", first_pitcher),
            (season * 10 + 2, f"{season}-09-30", last_pitcher),
        )
        for game_pk, game_date, (pitcher_id, pitcher_name, pitches) in game_rows:
            snapshot.games[game_pk] = _game_record(game_pk, game_date, season)
            snapshot.fetch_state[game_pk] = FetchStateRecord(
                game_pk, "success", NOW, NOW, None, 1,
            )
            snapshot.appearances[(game_pk, 100, pitcher_id)] = AppearanceRecord(
                game_pk, game_date, season, 100, "Club", pitcher_id, pitcher_name, pitches,
                True, 0, "SP", "official starter",
            )
            snapshot.appearances[(game_pk, 200, 2000)] = AppearanceRecord(
                game_pk, game_date, season, 200, "Opponent", 2000, "Opponent Starter", 10,
                True, 0, "SP", "official starter",
            )
        if stale_second_game:
            game_pk = season * 10 + 2
            snapshot.fetch_state[game_pk] = FetchStateRecord(
                game_pk, "failed", NOW, NOW, "temporary upstream failure", 2,
            )
        write_snapshot(snapshot, {
            "result": "partial" if stale_second_game else "complete", "generated_at": NOW, "api_calls": 2,
            "scheduled_games": 2, "games_requested": 2, "games_fetched": 1 if stale_second_game else 2,
            "games_failed": int(stale_second_game), "current_games": 1 if stale_second_game else 2,
            "stale_games": int(stale_second_game), "missing_games": 0,
        }, tmp_path)

    for season, pitches in ((2023, 80), (2024, 90), (2025, 100)):
        write_season(season, (1000, "Opening Starter", 10), (11, "Veteran", pitches))
    write_season(2026, (12, "Newcomer", 70), (11, "Veteran", 110))

    payload = export_player_history(tmp_path, 2026)
    veteran = payload["players"][0]
    newcomer = payload["players"][1]
    assert payload["historical_seasons"] == [2023, 2024, 2025]
    assert veteran["pitcher_id"] == 11
    assert [season["total"] for season in veteran["seasons"]] == [80, 90, 100, 110]
    assert veteran["seasons"][0]["points"] == [{"day": 184, "pitches": 80}]
    assert [season["total"] for season in newcomer["seasons"]] == [0, 0, 0, 70]
    assert all(not season["points"] for season in newcomer["seasons"][:3])

    write_season(
        2025,
        (1000, "Opening Starter", 10),
        (11, "Veteran", 100),
        stale_second_game=True,
    )
    with pytest.raises(ValueError, match=r"completed-season snapshot 2025 has incomplete coverage"):
        export_player_history(tmp_path, 2026)


def test_team_pitcher_usage_keeps_swingman_pitches_in_each_appearance_role():
    snapshot = Snapshot(season=2026)
    rows = [
        AppearanceRecord(
            1, "2026-07-19", 2026, 100, "Test Team", 1, "Swingman", 80,
            True, 0, "SP", "official starter",
        ),
        AppearanceRecord(
            2, "2026-07-20", 2026, 100, "Test Team", 1, "Swingman", 20,
            False, 1, "SP", "starter-identity bulk appearance",
        ),
        AppearanceRecord(
            2, "2026-07-20", 2026, 100, "Test Team", 2, "Reliever", 70,
            False, 2, "RP", "official reliever",
        ),
        AppearanceRecord(
            2, "2026-07-20", 2026, 100, "Test Team", 3, "Opener", 40,
            True, 0, "RP", "relief-dominant opener",
        ),
    ]
    for row in rows:
        snapshot.appearances[row.key] = row

    usage = aggregate_team_pitcher_usage(snapshot)[0]
    assert [row["pitcher_name"] for row in usage["total"]] == [
        "Swingman", "Reliever", "Opener",
    ]
    assert [(row["pitcher_name"], row["official_sp"]) for row in usage["official_sp"]] == [
        ("Swingman", 80), ("Opener", 40),
    ]
    assert [(row["pitcher_name"], row["official_rp"]) for row in usage["official_rp"]] == [
        ("Reliever", 70), ("Swingman", 20),
    ]
    assert [(row["pitcher_name"], row["adjusted_sp"]) for row in usage["adjusted_sp"]] == [
        ("Swingman", 100),
    ]
    assert [(row["pitcher_name"], row["adjusted_rp"]) for row in usage["adjusted_rp"]] == [
        ("Reliever", 70), ("Opener", 40),
    ]
