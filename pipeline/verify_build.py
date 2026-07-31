from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from .export import reconcile_team_timeseries
from .schema import SCHEMA_VERSION


class BrowserPayloadValidationError(ValueError):
    """Raised when a compiled dashboard payload is unsafe to publish."""


def _load_single_json(data_dir: Path, pattern: str, label: str) -> dict[str, Any]:
    files = list(data_dir.glob(pattern))
    if len(files) != 1:
        raise BrowserPayloadValidationError(
            f"expected one {label} payload, found {len(files)}"
        )
    try:
        payload = json.loads(files[0].read_text())
    except json.JSONDecodeError as exc:
        raise BrowserPayloadValidationError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BrowserPayloadValidationError(f"{label} payload must be an object")
    return payload


def verify_browser_payload(
    dist_dir: Path,
    *,
    expected_season: int,
    expected_data_commit: str,
) -> dict[str, int]:
    """Validate the compiled real-data payload before Pages deployment."""
    data_dir = dist_dir / "_file" / "data"
    payload = _load_single_json(data_dir, "dashboard.*.json", "dashboard")
    series = _load_single_json(data_dir, "team-timeseries.*.json", "team-timeseries")
    player_history = _load_single_json(data_dir, "player-history.*.json", "player-history")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPayloadValidationError("dashboard has an unsupported schema version")
    if series.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPayloadValidationError(
            "team-timeseries has an unsupported schema version"
        )
    if player_history.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPayloadValidationError(
            "player-history has an unsupported schema version"
        )
    if payload.get("season") != expected_season:
        raise BrowserPayloadValidationError("built the wrong season")
    if series.get("season") != payload["season"]:
        raise BrowserPayloadValidationError(
            "team-timeseries season does not match dashboard"
        )
    if player_history.get("season") != payload["season"]:
        raise BrowserPayloadValidationError(
            "player-history season does not match dashboard"
        )

    teams = payload.get("teams")
    if not isinstance(teams, list) or len(teams) != 30:
        found = len(teams) if isinstance(teams, list) else "invalid"
        raise BrowserPayloadValidationError(f"expected 30 MLB teams, found {found}")
    team_ids = {row.get("team_id") for row in teams}
    if len(team_ids) != len(teams) or any(not isinstance(team_id, int) for team_id in team_ids):
        raise BrowserPayloadValidationError("dashboard teams have invalid or duplicate ids")

    player_totals = payload.get("player_totals")
    if not isinstance(player_totals, list) or len(player_totals) != 30:
        raise BrowserPayloadValidationError(
            "dashboard must include exactly 30 player totals"
        )
    if len({row.get("pitcher_id") for row in player_totals}) != len(player_totals):
        raise BrowserPayloadValidationError("player totals contain duplicate pitchers")
    if any(
        not isinstance(row.get("pitcher_id"), int)
        or not isinstance(row.get("pitcher_name"), str)
        or not isinstance(row.get("team_id"), int)
        or not isinstance(row.get("team_name"), str)
        or not isinstance(row.get("total"), int)
        or row["total"] < 0
        for row in player_totals
    ):
        raise BrowserPayloadValidationError("player totals contain an invalid row")
    if player_totals != sorted(
        player_totals,
        key=lambda row: (-row["total"], row["pitcher_name"], row["pitcher_id"]),
    ):
        raise BrowserPayloadValidationError("player totals are not ranked by total pitches")

    historical_seasons = player_history.get("historical_seasons")
    expected_historical_seasons = list(range(expected_season - 3, expected_season))
    if historical_seasons != expected_historical_seasons:
        raise BrowserPayloadValidationError(
            "player-history must contain exactly the three completed prior seasons"
        )
    historical_players = player_history.get("players")
    if not isinstance(historical_players, list) or len(historical_players) != len(player_totals):
        raise BrowserPayloadValidationError(
            "player-history must contain one record for every current player leader"
        )
    if [player.get("pitcher_id") for player in historical_players] != [
        player["pitcher_id"] for player in player_totals
    ]:
        raise BrowserPayloadValidationError(
            "player-history players do not match the ranked player leaders"
        )
    expected_history_seasons = [*expected_historical_seasons, expected_season]
    for leader, history in zip(player_totals, historical_players, strict=True):
        if history.get("pitcher_name") != leader["pitcher_name"]:
            raise BrowserPayloadValidationError(
                "player-history pitcher name does not match the player leader"
            )
        seasons = history.get("seasons")
        if not isinstance(seasons, list) or [row.get("season") for row in seasons] != expected_history_seasons:
            raise BrowserPayloadValidationError(
                "player-history has an invalid season sequence"
            )
        for season_row in seasons:
            season_days = season_row.get("season_days")
            total = season_row.get("total")
            appearances = season_row.get("appearances")
            points = season_row.get("points")
            if (
                not isinstance(season_days, int)
                or season_days < 0
                or not isinstance(total, int)
                or total < 0
                or not isinstance(appearances, int)
                or appearances < 0
                or not isinstance(points, list)
            ):
                raise BrowserPayloadValidationError("player-history has invalid season metrics")
            if any(
                not isinstance(point.get("day"), int)
                or point["day"] < 0
                or point["day"] > season_days
                or not isinstance(point.get("pitches"), int)
                or point["pitches"] <= 0
                for point in points
            ):
                raise BrowserPayloadValidationError("player-history has an invalid pitch point")
            if points != sorted(points, key=lambda point: point["day"]) or len({point["day"] for point in points}) != len(points):
                raise BrowserPayloadValidationError(
                    "player-history pitch points must have unique ordered days"
                )
            if sum(point["pitches"] for point in points) != total or appearances < len(points):
                raise BrowserPayloadValidationError(
                    "player-history season totals do not reconcile to pitch points"
                )
        if seasons[-1]["total"] != leader["total"]:
            raise BrowserPayloadValidationError(
                "player-history current-season total does not match the player leader"
            )

    team_pitcher_usage = payload.get("team_pitcher_usage")
    if not isinstance(team_pitcher_usage, list) or len(team_pitcher_usage) != len(teams):
        raise BrowserPayloadValidationError(
            "dashboard missing one team pitcher-usage record per team"
        )
    if {row.get("team_id") for row in team_pitcher_usage} != team_ids:
        raise BrowserPayloadValidationError(
            "pitcher-usage teams do not match season teams"
        )
    usage_keys = ("total", "official_sp", "official_rp", "adjusted_sp", "adjusted_rp")
    for usage in team_pitcher_usage:
        if not isinstance(usage.get("team_name"), str):
            raise BrowserPayloadValidationError("pitcher usage has an invalid team name")
        for key in usage_keys:
            pitchers = usage.get(key)
            if not isinstance(pitchers, list) or len(pitchers) > 5:
                raise BrowserPayloadValidationError(
                    "pitcher usage list must contain at most five pitchers"
                )
            if len({pitcher.get("pitcher_id") for pitcher in pitchers}) != len(pitchers):
                raise BrowserPayloadValidationError(
                    "pitcher usage list contains duplicate pitchers"
                )
            if any(
                not isinstance(pitcher.get("pitcher_id"), int)
                or not isinstance(pitcher.get("pitcher_name"), str)
                or any(
                    not isinstance(pitcher.get(metric), int) or pitcher[metric] < 0
                    for metric in usage_keys
                )
                or pitcher[key] <= 0
                for pitcher in pitchers
            ):
                raise BrowserPayloadValidationError("pitcher usage contains an invalid row")
            if pitchers != sorted(
                pitchers,
                key=lambda pitcher: (
                    -pitcher[key],
                    pitcher["pitcher_name"],
                    pitcher["pitcher_id"],
                ),
            ):
                raise BrowserPayloadValidationError(
                    "pitcher usage list is not ranked by its workload"
                )

    recent_games = payload.get("recent_games")
    if not isinstance(recent_games, list) or len(recent_games) != len(teams):
        raise BrowserPayloadValidationError(
            "dashboard missing one latest completed game per team"
        )
    if {row.get("team_id") for row in recent_games} != team_ids:
        raise BrowserPayloadValidationError(
            "recent-game teams do not match season teams"
        )
    if any(not row.get("pitchers") for row in recent_games):
        raise BrowserPayloadValidationError("recent game has no pitcher workloads")

    next_games = payload.get("next_games")
    if not isinstance(next_games, list):
        raise BrowserPayloadValidationError("next_games must be a list")
    if next_games:
        if len(next_games) != len(teams):
            raise BrowserPayloadValidationError(
                "dashboard missing one next game per team"
            )
        if {row.get("team_id") for row in next_games} != team_ids:
            raise BrowserPayloadValidationError(
                "next-game teams do not match season teams"
            )
        for game in next_games:
            if game.get("team_id") == game.get("opponent_id"):
                raise BrowserPayloadValidationError(
                    "next game has the same team and opponent"
                )
            pitcher_id = game.get("probable_pitcher_id")
            pitcher_name = game.get("probable_pitcher_name")
            if (pitcher_id is None) != (pitcher_name is None):
                raise BrowserPayloadValidationError(
                    "next game has incomplete probable-pitcher data"
                )
            is_rest_day_today = game.get("is_rest_day_today", False)
            schedule_date = game.get("schedule_date")
            if not isinstance(is_rest_day_today, bool):
                raise BrowserPayloadValidationError(
                    "is_rest_day_today must be a boolean"
                )
            if schedule_date is not None and not isinstance(schedule_date, str):
                raise BrowserPayloadValidationError(
                    "schedule_date must be a string or null"
                )
            if is_rest_day_today and not schedule_date:
                raise BrowserPayloadValidationError(
                    "rest-day next game is missing its schedule date"
                )
            starts = game.get("probable_recent_starts")
            if not isinstance(starts, list) or len(starts) > 3:
                raise BrowserPayloadValidationError(
                    "probable_recent_starts must be a list of at most 3 starts"
                )
            days_rest = game.get("probable_days_rest")
            if pitcher_id is None:
                if starts or days_rest is not None:
                    raise BrowserPayloadValidationError(
                        "unannounced probable starter must have empty start history"
                    )
            elif days_rest is not None and (
                not isinstance(days_rest, int) or days_rest < 0
            ):
                raise BrowserPayloadValidationError(
                    "probable_days_rest must be a non-negative int or null"
                )
            for start in starts:
                if not isinstance(start.get("pitches"), int) or start["pitches"] < 0:
                    raise BrowserPayloadValidationError(
                        "probable start pitches must be a non-negative int"
                    )
                if "date" not in start or "game_pk" not in start:
                    raise BrowserPayloadValidationError(
                        "probable start missing date or game_pk"
                    )

    bullpen_usage = payload.get("bullpen_usage")
    if not isinstance(bullpen_usage, list) or len(bullpen_usage) != len(teams):
        raise BrowserPayloadValidationError(
            "dashboard missing one bullpen-usage window per team"
        )
    if {row.get("team_id") for row in bullpen_usage} != team_ids:
        raise BrowserPayloadValidationError(
            "bullpen-usage teams do not match season teams"
        )
    for usage in bullpen_usage:
        dates = usage.get("dates")
        if (
            not isinstance(dates, list)
            or len(dates) != 14
            or dates != sorted(set(dates))
        ):
            raise BrowserPayloadValidationError(
                "bullpen-usage window must contain 14 unique ordered dates"
            )
        if usage.get("end_date") != dates[-1]:
            raise BrowserPayloadValidationError(
                "bullpen-usage end date does not match its final date"
            )
        pitchers = usage.get("pitchers")
        if not isinstance(pitchers, list):
            raise BrowserPayloadValidationError(
                "bullpen-usage pitchers must be a list"
            )
        if any(
            len(pitcher.get("pitches", [])) != len(dates)
            or any(
                not isinstance(value, int) or value < 0
                for value in pitcher["pitches"]
            )
            for pitcher in pitchers
        ):
            raise BrowserPayloadValidationError(
                "bullpen-usage pitch arrays do not match the date window"
            )
        for pitcher in pitchers:
            if "on_depth_chart" in pitcher and not isinstance(
                pitcher["on_depth_chart"], bool
            ):
                raise BrowserPayloadValidationError(
                    "bullpen-usage on_depth_chart must be a boolean when present"
                )
            availability = pitcher.get("availability")
            if availability is not None and not isinstance(availability, str):
                raise BrowserPayloadValidationError(
                    "bullpen-usage availability must be a string or null"
                )

    starter_rest = payload.get("starter_rest")
    if not isinstance(starter_rest, list) or len(starter_rest) != len(teams):
        raise BrowserPayloadValidationError(
            "dashboard missing one starter-rest record per team"
        )
    if {row.get("team_id") for row in starter_rest} != team_ids:
        raise BrowserPayloadValidationError(
            "starter-rest teams do not match season teams"
        )
    for rest in starter_rest:
        if not isinstance(rest.get("team_name"), str) or not rest["team_name"]:
            raise BrowserPayloadValidationError(
                "starter-rest has an invalid team name"
            )
        as_of_value = rest.get("as_of_date")
        if not isinstance(as_of_value, str):
            raise BrowserPayloadValidationError(
                "starter-rest as-of date must be a string"
            )
        try:
            as_of_date = date.fromisoformat(as_of_value)
        except ValueError as exc:
            raise BrowserPayloadValidationError(
                "starter-rest has an invalid as-of date"
            ) from exc
        pitchers = rest.get("pitchers")
        if not isinstance(pitchers, list):
            raise BrowserPayloadValidationError(
                "starter-rest pitchers must be a list"
            )
        if len({pitcher.get("pitcher_id") for pitcher in pitchers}) != len(pitchers):
            raise BrowserPayloadValidationError(
                "starter-rest list contains duplicate pitchers"
            )
        if pitchers != sorted(
            pitchers,
            key=lambda pitcher: (
                (
                    pitcher.get("depth_order")
                    if isinstance(pitcher.get("depth_order"), int)
                    else 10**9
                ),
                (
                    pitcher.get("pitcher_name")
                    if isinstance(pitcher.get("pitcher_name"), str)
                    else ""
                ),
                (
                    pitcher.get("pitcher_id")
                    if isinstance(pitcher.get("pitcher_id"), int)
                    else 10**9
                ),
            ),
        ):
            raise BrowserPayloadValidationError(
                "starter-rest pitchers are not in depth-chart order"
            )
        for pitcher in pitchers:
            if (
                not isinstance(pitcher.get("pitcher_id"), int)
                or not isinstance(pitcher.get("pitcher_name"), str)
                or not pitcher["pitcher_name"]
                or pitcher.get("depth_role") != "SP"
                or not isinstance(pitcher.get("depth_order"), int)
                or pitcher["depth_order"] < 0
                or pitcher.get("status_code") != "A"
                or (
                    pitcher.get("jersey_number") is not None
                    and not isinstance(pitcher["jersey_number"], str)
                )
            ):
                raise BrowserPayloadValidationError(
                    "starter-rest contains an invalid active starter row"
                )
            last_start_value = pitcher.get("last_start_date")
            last_start_pitches = pitcher.get("last_start_pitches")
            days_rest = pitcher.get("days_rest")
            if last_start_value is None:
                if last_start_pitches is not None or days_rest is not None:
                    raise BrowserPayloadValidationError(
                        "starter without start history must have null workload context"
                    )
                continue
            if (
                not isinstance(last_start_value, str)
                or not isinstance(last_start_pitches, int)
                or last_start_pitches <= 0
                or not isinstance(days_rest, int)
                or days_rest < 0
            ):
                raise BrowserPayloadValidationError(
                    "starter-rest contains invalid start history"
                )
            try:
                last_start_date = date.fromisoformat(last_start_value)
            except ValueError as exc:
                raise BrowserPayloadValidationError(
                    "starter-rest has an invalid last-start date"
                ) from exc
            expected_days_rest = max(0, (as_of_date - last_start_date).days - 1)
            if last_start_date > as_of_date or days_rest != expected_days_rest:
                raise BrowserPayloadValidationError(
                    "starter-rest days do not match its dates"
                )

    status = payload.get("status")
    if not isinstance(status, dict) or status.get("result") not in {
        "complete",
        "partial",
    }:
        raise BrowserPayloadValidationError(
            "refusing to deploy a failed or invalid data snapshot"
        )
    if payload.get("data_commit") != expected_data_commit:
        raise BrowserPayloadValidationError(
            "dashboard data revision does not match checked-out data"
        )
    if series.get("data_commit") != payload["data_commit"]:
        raise BrowserPayloadValidationError(
            "team-timeseries data revision does not match dashboard"
        )
    if player_history.get("data_commit") != payload["data_commit"]:
        raise BrowserPayloadValidationError(
            "player-history data revision does not match dashboard"
        )
    points = series.get("points")
    if not isinstance(points, list):
        raise BrowserPayloadValidationError("team-timeseries points must be a list")
    complete_games = series.get("complete_games")
    if not isinstance(complete_games, list):
        raise BrowserPayloadValidationError(
            "team-timeseries missing complete_games list"
        )
    reconcile_team_timeseries(teams, points)

    index_path = dist_dir / "index.html"
    if not index_path.exists():
        raise BrowserPayloadValidationError("compiled dashboard is missing index.html")
    if "_node/react@" in index_path.read_text():
        raise BrowserPayloadValidationError(
            "built dashboard contains a second React runtime"
        )

    return {
        "teams": len(teams),
        "team_day_points": len(points),
        "complete_games": len(complete_games),
        "player_totals": len(player_totals),
        "player_history_players": len(historical_players),
        "team_usage_windows": len(team_pitcher_usage),
        "recent_games": len(recent_games),
        "next_games": len(next_games),
        "bullpen_windows": len(bullpen_usage),
        "starter_rest_records": len(starter_rest),
        "current_games": int(status.get("current_games", 0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the compiled MLB dashboard before Pages deployment"
    )
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--season", type=int)
    parser.add_argument("--data-commit")
    args = parser.parse_args()

    expected_season = args.season
    if expected_season is None:
        season_value = os.getenv("DASHBOARD_SEASON")
        if season_value is None:
            parser.error("--season or DASHBOARD_SEASON is required")
        try:
            expected_season = int(season_value)
        except ValueError:
            parser.error("DASHBOARD_SEASON must be an integer")

    expected_data_commit = args.data_commit or os.getenv("DASHBOARD_DATA_SHA")
    if not expected_data_commit:
        parser.error("--data-commit or DASHBOARD_DATA_SHA is required")

    result = verify_browser_payload(
        args.dist_dir,
        expected_season=expected_season,
        expected_data_commit=expected_data_commit,
    )
    print(
        f"Validated {result['teams']} teams, {result['team_day_points']} "
        f"team-day points, {result['complete_games']} complete games, "
        f"{result['player_totals']} player totals, "
        f"{result['player_history_players']} player histories, "
        f"{result['team_usage_windows']} team usage windows, "
        f"{result['recent_games']} recent team games, "
        f"{result['next_games']} next team games, "
        f"{result['bullpen_windows']} bullpen windows, "
        f"{result['starter_rest_records']} starter-rest records, and "
        f"{result['current_games']} current games"
    )


if __name__ == "__main__":
    main()
