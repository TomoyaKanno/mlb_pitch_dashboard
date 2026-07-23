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


def _game(
    game_pk: int,
    game_date: str,
    away_id: int,
    home_id: int,
    *,
    state: str,
    detailed_state: str,
) -> dict:
    return {
        "gamePk": game_pk,
        "officialDate": game_date,
        "gameDate": game_date + "T23:10:00Z",
        "status": {
            "abstractGameState": state,
            "detailedState": detailed_state,
        },
        "teams": {
            "away": {"team": {"id": away_id, "name": f"Away {away_id}"}},
            "home": {"team": {"id": home_id, "name": f"Home {home_id}"}},
        },
    }


def test_eastern_today_uses_the_eastern_calendar_boundary() -> None:
    assert mlb.eastern_today(datetime(2026, 7, 24, 2, tzinfo=timezone.utc)) == date(2026, 7, 23)


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
                _game(2, today, 5, 6, state="Final", detailed_state="Postponed"),
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
