from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from pipeline import mlb


class _ScheduleClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.params: dict | None = None

    async def get_json(self, path: str, params: dict | None = None) -> dict:
        assert path == "/schedule"
        self.params = params
        return self.payload


class _RoutingClient:
    def __init__(self, payloads: dict) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict | None]] = []

    async def get_json(self, path: str, params: dict | None = None) -> dict:
        self.calls.append((path, params))
        roster_type = params.get("rosterType") if params else None
        key = (path, roster_type)
        return self.payloads[key] if key in self.payloads else self.payloads[path]


def _game(
    game_pk: int,
    game_date: str,
    away_id: int,
    home_id: int,
    *,
    state: str,
    detailed_state: str,
    game_datetime: str | None = None,
    away_probable: tuple[int, str] | None = None,
    home_probable: tuple[int, str] | None = None,
) -> dict:
    away: dict = {"team": {"id": away_id, "name": f"Away {away_id}"}}
    home: dict = {"team": {"id": home_id, "name": f"Home {home_id}"}}
    if away_probable:
        away["probablePitcher"] = {"id": away_probable[0], "fullName": away_probable[1]}
    if home_probable:
        home["probablePitcher"] = {"id": home_probable[0], "fullName": home_probable[1]}
    return {
        "gamePk": game_pk,
        "officialDate": game_date,
        "gameDate": game_datetime or game_date + "T23:10:00Z",
        "status": {
            "abstractGameState": state,
            "detailedState": detailed_state,
        },
        "teams": {
            "away": away,
            "home": home,
        },
    }


def test_eastern_today_uses_the_eastern_calendar_boundary() -> None:
    assert mlb.eastern_today(datetime(2026, 7, 24, 2, tzinfo=timezone.utc)) == date(2026, 7, 23)


def test_completed_games_filters_nonfinal_games_and_preserves_schedule_context(
    monkeypatch,
) -> None:
    client = _ScheduleClient({
        "dates": [{
            "date": "2026-07-22",
            "games": [
                _game(
                    2, "2026-07-22", 3, 4,
                    state="Final", detailed_state="Final",
                    game_datetime="2026-07-22T23:10:00Z",
                ),
                _game(
                    1, "2026-07-22", 1, 2,
                    state="Final", detailed_state="Completed Early",
                    game_datetime="2026-07-22T17:10:00Z",
                ),
                _game(3, "2026-07-22", 5, 6, state="Preview", detailed_state="Scheduled"),
                _game(4, "2026-07-22", 7, 8, state="Final", detailed_state="Postponed"),
            ],
        }, {
            "date": "2026-07-24",
            "games": [
                _game(5, "2026-07-24", 9, 10, state="Final", detailed_state="Final"),
            ],
        }],
    })
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    rows = asyncio.run(mlb.MLBClient.completed_games(client, 2026))

    assert client.params == {
        "sportId": 1,
        "gameType": "R",
        "startDate": "2026-03-01",
        "endDate": "2026-07-23",
    }
    assert [row["game_pk"] for row in rows] == [1, 2]
    assert rows[0] == {
        "game_pk": 1,
        "game_date": "2026-07-22",
        "season": 2026,
        "status": "Completed Early",
        "game_datetime": "2026-07-22T17:10:00Z",
        "away_team_id": 1,
        "away_team_name": "Away 1",
        "home_team_id": 2,
        "home_team_name": "Home 2",
    }


def test_completed_games_uses_full_regular_season_window_for_historical_season(
    monkeypatch,
) -> None:
    client = _ScheduleClient({"dates": []})
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    assert asyncio.run(mlb.MLBClient.completed_games(client, 2025)) == []
    assert client.params["endDate"] == "2025-11-15"


def test_upcoming_games_marks_rest_only_when_team_absent_from_entire_todays_slate(
    monkeypatch,
) -> None:
    today = "2026-07-23"
    tomorrow = "2026-07-24"
    client = _ScheduleClient({
        "dates": [{
            "date": today,
            "games": [
                # Final games still count as a game today.
                _game(1, today, 1, 2, state="Final", detailed_state="Final"),
                # Disrupted games also suppress the rest-day statement.
                _game(2, today, 5, 6, state="Preview", detailed_state="Postponed"),
            ],
        }, {
            "date": tomorrow,
            "games": [
                _game(3, tomorrow, 1, 3, state="Preview", detailed_state="Scheduled"),
                _game(4, tomorrow, 2, 4, state="Preview", detailed_state="Scheduled"),
                _game(5, tomorrow, 5, 7, state="Preview", detailed_state="Scheduled"),
                _game(6, tomorrow, 6, 8, state="Preview", detailed_state="Scheduled"),
            ],
        }],
    })
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    rows = asyncio.run(mlb.MLBClient.upcoming_games(client, 2026))
    by_team = {row["team_id"]: row for row in rows}

    assert client.params == {
        "sportId": 1,
        "gameType": "R",
        "startDate": today,
        "endDate": "2026-08-06",
        "hydrate": "probablePitcher",
    }
    assert by_team[1]["is_rest_day_today"] is False
    assert by_team[2]["is_rest_day_today"] is False
    assert by_team[5]["is_rest_day_today"] is False
    assert by_team[6]["is_rest_day_today"] is False
    assert by_team[3]["is_rest_day_today"] is True
    assert by_team[4]["is_rest_day_today"] is True
    assert by_team[7]["is_rest_day_today"] is True
    assert by_team[8]["is_rest_day_today"] is True
    assert {row["schedule_date"] for row in rows} == {today}


def test_upcoming_games_selects_the_earliest_game_and_exports_probable_pitchers(
    monkeypatch,
) -> None:
    today = "2026-07-23"
    client = _ScheduleClient({
        "dates": [{
            "date": today,
            "games": [
                _game(
                    20, today, 1, 2,
                    state="Preview", detailed_state="Scheduled",
                    game_datetime="2026-07-23T23:10:00Z",
                    away_probable=(101, "Away Starter"),
                ),
                _game(
                    10, today, 1, 3,
                    state="Preview", detailed_state="Scheduled",
                    game_datetime="2026-07-23T17:10:00Z",
                    away_probable=(102, "Earlier Starter"),
                    home_probable=(103, "Home Starter"),
                ),
            ],
        }],
    })
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    rows = asyncio.run(mlb.MLBClient.upcoming_games(client, 2026))
    by_team = {row["team_id"]: row for row in rows}

    assert by_team[1]["game_pk"] == 10
    assert by_team[1]["probable_pitcher_id"] == 102
    assert by_team[1]["probable_pitcher_name"] == "Earlier Starter"
    assert by_team[3]["probable_pitcher_id"] == 103
    assert by_team[2]["game_pk"] == 20
    assert by_team[2]["probable_pitcher_id"] is None


def test_upcoming_games_and_rosters_skip_historical_seasons(monkeypatch) -> None:
    client = _RoutingClient({})
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    assert asyncio.run(mlb.MLBClient.upcoming_games(client, 2025)) == []
    assert asyncio.run(mlb.MLBClient.pitching_rosters(client, 2025)) == []
    assert client.calls == []


def test_pitching_rosters_merge_depth_order_with_latest_40_man_status(monkeypatch) -> None:
    client = _RoutingClient({
        "/teams": {"teams": [{"id": 17, "name": "Test Team"}]},
        ("/teams/17/roster", "depthChart"): {
            "roster": [
                {
                    "person": {"id": 1, "fullName": "Starter"},
                    "position": {"abbreviation": "SP"},
                    "status": {"code": "A", "description": "Active"},
                },
                {
                    "person": {"id": 2, "fullName": "Reliever"},
                    "position": {"abbreviation": "P"},
                    "status": {"code": "A", "description": "Active"},
                },
                {
                    "person": {"id": 3, "fullName": "Closer"},
                    "position": {"abbreviation": "CP"},
                    "status": {"code": "A", "description": "Active"},
                },
                {
                    "person": {"id": 99, "fullName": "Position Player"},
                    "position": {"abbreviation": "1B"},
                    "status": {"code": "A", "description": "Active"},
                },
            ],
        },
        ("/teams/17/roster", "40Man"): {
            "roster": [
                {
                    "person": {"id": 1, "fullName": "Starter"},
                    "position": {"type": "Pitcher", "abbreviation": "SP"},
                    "status": {"code": "D15", "description": "15-day IL"},
                },
                {
                    "person": {"id": 4, "fullName": "Two Way"},
                    "position": {"type": "Two-Way Player", "abbreviation": "TWP"},
                    "status": {"code": "A", "description": "Active"},
                },
                {
                    "person": {"id": 5, "fullName": "Minors Arm"},
                    "position": {"type": "Pitcher", "abbreviation": "P"},
                    "status": {"code": "RM", "description": "Reassigned"},
                },
                {
                    "person": {"id": 98, "fullName": "Catcher"},
                    "position": {"type": "Catcher", "abbreviation": "C"},
                    "status": {"code": "A", "description": "Active"},
                },
            ],
        },
    })
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    rows = asyncio.run(mlb.MLBClient.pitching_rosters(client, 2026))
    by_id = {row["pitcher_id"]: row for row in rows}

    assert [row["pitcher_id"] for row in rows] == [1, 2, 3, 98, 5, 4]
    assert by_id[1]["depth_role"] == "SP"
    assert by_id[1]["depth_order"] == 0
    assert by_id[1]["status_code"] == "D15"
    assert by_id[2]["depth_role"] == "RP"
    assert by_id[3]["depth_role"] == "CP"
    assert by_id[4]["depth_role"] is None
    assert by_id[5]["status_description"] == "Reassigned"
    # The 40-man is captured whole: an active catcher pressed into mop-up
    # relief must resolve to a roster row, never to a departed-arm state.
    assert by_id[98]["depth_role"] is None
    assert by_id[98]["status_code"] == "A"
    assert 99 not in by_id


def test_pitching_rosters_returns_empty_when_mlb_returns_no_teams(monkeypatch) -> None:
    client = _RoutingClient({"/teams": {"teams": []}})
    monkeypatch.setattr(mlb, "eastern_today", lambda: date(2026, 7, 23))

    assert asyncio.run(mlb.MLBClient.pitching_rosters(client, 2026)) == []
    assert client.calls == [("/teams", {"sportId": 1, "season": 2026})]


def test_boxscore_appearances_preserve_pitcher_order_and_official_start() -> None:
    client = _RoutingClient({
        "/game/7/boxscore": {
            "teams": {
                "away": {
                    "team": {"id": 1, "name": "Away"},
                    "pitchers": [11, 12, 13],
                    "players": {
                        "ID11": {
                            "person": {"fullName": "Away Starter"},
                            "stats": {"pitching": {"numberOfPitches": 80, "gamesStarted": 1}},
                        },
                        "ID12": {
                            "person": {"fullName": "No Pitches"},
                            "stats": {"pitching": {"numberOfPitches": 0, "gamesStarted": 0}},
                        },
                        "ID13": {
                            "person": {"fullName": "Away Reliever"},
                            "stats": {"pitching": {"numberOfPitches": 22, "gamesStarted": 0}},
                        },
                    },
                },
                "home": {
                    "team": {"id": 2, "name": "Home"},
                    "pitchers": [21],
                    "players": {
                        "ID21": {
                            "stats": {"pitching": {"numberOfPitches": "91", "gamesStarted": "1"}},
                        },
                    },
                },
            },
        },
    })

    rows = asyncio.run(mlb.MLBClient.boxscore_appearances(client, {"game_pk": 7}))

    assert rows == [
        {
            "game_pk": 7,
            "team_id": 1,
            "team_name": "Away",
            "pitcher_id": 11,
            "pitcher_name": "Away Starter",
            "pitches": 80,
            "official_started": True,
            "appearance_order": 0,
        },
        {
            "game_pk": 7,
            "team_id": 1,
            "team_name": "Away",
            "pitcher_id": 13,
            "pitcher_name": "Away Reliever",
            "pitches": 22,
            "official_started": False,
            "appearance_order": 2,
        },
        {
            "game_pk": 7,
            "team_id": 2,
            "team_name": "Home",
            "pitcher_id": 21,
            "pitcher_name": "Player 21",
            "pitches": 91,
            "official_started": True,
            "appearance_order": 0,
        },
    ]
