from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .export import reconcile_team_timeseries
from .schema import SCHEMA_VERSION


class BrowserPayloadValidationError(ValueError):
    """Raised when the compiled dashboard is not safe to publish."""


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


def _team_rows(
    payload: dict[str, Any],
    key: str,
    team_ids: set[int],
    label: str,
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise BrowserPayloadValidationError(f"{label} must be a list")
    if allow_empty and not rows:
        return rows
    row_ids = {
        row.get("team_id") if isinstance(row, dict) else None
        for row in rows
    }
    if len(rows) != len(team_ids) or row_ids != team_ids:
        raise BrowserPayloadValidationError(
            f"{label} must contain one record for every season team"
        )
    return rows


def verify_browser_payload(
    dist_dir: Path,
    *,
    expected_season: int,
    expected_data_commit: str,
) -> dict[str, int]:
    """Verify the compiled artifact and its cross-payload contracts."""
    data_dir = dist_dir / "_file" / "data"
    payload = _load_single_json(data_dir, "dashboard.*.json", "dashboard")
    series = _load_single_json(data_dir, "team-timeseries.*.json", "team-timeseries")
    player_history = _load_single_json(data_dir, "player-history.*.json", "player-history")

    artifacts = {
        "dashboard": payload,
        "team-timeseries": series,
        "player-history": player_history,
    }
    for label, artifact in artifacts.items():
        if artifact.get("schema_version") != SCHEMA_VERSION:
            raise BrowserPayloadValidationError(f"{label} has an unsupported schema version")
        if artifact.get("season") != expected_season:
            raise BrowserPayloadValidationError(f"{label} was built for the wrong season")
        if artifact.get("data_commit") != expected_data_commit:
            raise BrowserPayloadValidationError(
                f"{label} data revision does not match checked-out data"
            )

    status = payload.get("status")
    if not isinstance(status, dict) or status.get("result") not in {"complete", "partial"}:
        raise BrowserPayloadValidationError(
            "refusing to deploy a failed or invalid data snapshot"
        )

    teams = payload.get("teams")
    if not isinstance(teams, list) or len(teams) != 30:
        found = len(teams) if isinstance(teams, list) else "invalid"
        raise BrowserPayloadValidationError(f"expected 30 MLB teams, found {found}")
    team_ids = {
        row.get("team_id") if isinstance(row, dict) else None
        for row in teams
    }
    if len(team_ids) != 30 or any(not isinstance(team_id, int) for team_id in team_ids):
        raise BrowserPayloadValidationError("dashboard teams have invalid or duplicate ids")

    player_totals = payload.get("player_totals")
    if not isinstance(player_totals, list) or len(player_totals) != 30:
        raise BrowserPayloadValidationError("dashboard must include exactly 30 player totals")
    leaders = {
        row.get("pitcher_id"): row
        for row in player_totals
        if isinstance(row, dict) and isinstance(row.get("pitcher_id"), int)
    }
    if len(leaders) != 30:
        raise BrowserPayloadValidationError("player totals contain invalid or duplicate pitchers")

    expected_historical_seasons = list(range(expected_season - 3, expected_season))
    if player_history.get("historical_seasons") != expected_historical_seasons:
        raise BrowserPayloadValidationError(
            "player-history must contain the three completed prior seasons"
        )
    historical_players = player_history.get("players")
    if not isinstance(historical_players, list):
        raise BrowserPayloadValidationError("player-history players must be a list")
    histories = {
        row.get("pitcher_id"): row
        for row in historical_players
        if isinstance(row, dict) and isinstance(row.get("pitcher_id"), int)
    }
    if set(histories) != set(leaders) or len(historical_players) != len(leaders):
        raise BrowserPayloadValidationError(
            "player-history players do not match the current player leaders"
        )
    expected_history_seasons = [*expected_historical_seasons, expected_season]
    for pitcher_id, leader in leaders.items():
        history = histories[pitcher_id]
        seasons = history.get("seasons")
        if not isinstance(seasons, list) or [row.get("season") for row in seasons] != expected_history_seasons:
            raise BrowserPayloadValidationError("player-history has an invalid season sequence")
        if seasons[-1].get("total") != leader.get("total"):
            raise BrowserPayloadValidationError(
                "player-history current total does not match the player leader"
            )

    usage_keys = ("total", "official_sp", "official_rp", "adjusted_sp", "adjusted_rp")
    team_pitcher_usage = _team_rows(
        payload, "team_pitcher_usage", team_ids, "team pitcher usage"
    )
    if any(
        not isinstance(usage.get(key), list) or len(usage[key]) > 5
        for usage in team_pitcher_usage
        for key in usage_keys
    ):
        raise BrowserPayloadValidationError(
            "team pitcher usage must provide five lists of at most five pitchers"
        )

    recent_games = _team_rows(payload, "recent_games", team_ids, "recent games")
    if any(not isinstance(row.get("pitchers"), list) or not row["pitchers"] for row in recent_games):
        raise BrowserPayloadValidationError("recent game has no pitcher workloads")

    next_games = _team_rows(
        payload, "next_games", team_ids, "next games", allow_empty=True
    )

    bullpen_usage = _team_rows(
        payload, "bullpen_usage", team_ids, "bullpen usage"
    )
    for usage in bullpen_usage:
        dates = usage.get("dates")
        pitchers = usage.get("pitchers")
        if (
            not isinstance(dates, list)
            or len(dates) != 14
            or usage.get("end_date") != dates[-1]
            or not isinstance(pitchers, list)
            or any(
                not isinstance(pitcher, dict)
                or not isinstance(pitcher.get("pitches"), list)
                or len(pitcher["pitches"]) != len(dates)
                for pitcher in pitchers
            )
        ):
            raise BrowserPayloadValidationError(
                "bullpen usage does not match its 14-day display contract"
            )

    starter_rest = _team_rows(
        payload, "starter_rest", team_ids, "starter rest"
    )
    if any(not isinstance(row.get("pitchers"), list) for row in starter_rest):
        raise BrowserPayloadValidationError("starter-rest pitchers must be a list")

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
