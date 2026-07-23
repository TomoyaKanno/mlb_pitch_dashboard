from __future__ import annotations

import argparse
import json
import os
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

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPayloadValidationError("dashboard has an unsupported schema version")
    if series.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPayloadValidationError(
            "team-timeseries has an unsupported schema version"
        )
    if payload.get("season") != expected_season:
        raise BrowserPayloadValidationError("built the wrong season")
    if series.get("season") != payload["season"]:
        raise BrowserPayloadValidationError(
            "team-timeseries season does not match dashboard"
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
        "team_usage_windows": len(team_pitcher_usage),
        "recent_games": len(recent_games),
        "next_games": len(next_games),
        "bullpen_windows": len(bullpen_usage),
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
        f"{result['team_usage_windows']} team usage windows, "
        f"{result['recent_games']} recent team games, "
        f"{result['next_games']} next team games, "
        f"{result['bullpen_windows']} bullpen windows, and "
        f"{result['current_games']} current games"
    )


if __name__ == "__main__":
    main()
