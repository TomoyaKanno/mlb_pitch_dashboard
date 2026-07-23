from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipeline.schema import SCHEMA_VERSION
from pipeline.verify_build import (
    BrowserPayloadValidationError,
    verify_browser_payload,
)


def _valid_payloads(data_commit: str = "data-sha") -> tuple[dict, dict]:
    teams = [
        {
            "team_id": team_id,
            "team_name": f"Team {team_id:02d}",
            "games": 1,
            "total": 10,
            "official_sp": 6,
            "official_rp": 4,
            "adjusted_sp": 6,
            "adjusted_rp": 4,
            "bulk_to_sp": 0,
            "opener_to_rp": 0,
            "review_count": 0,
        }
        for team_id in range(1, 31)
    ]
    player_totals = [
        {
            "pitcher_id": index,
            "pitcher_name": f"Pitcher {index:02d}",
            "team_id": index,
            "team_name": f"Team {index:02d}",
            "total": 101 - index,
        }
        for index in range(1, 31)
    ]
    usage = [
        {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "total": [],
            "official_sp": [],
            "official_rp": [],
            "adjusted_sp": [],
            "adjusted_rp": [],
        }
        for team in teams
    ]
    recent_games = [
        {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "pitchers": [{"pitcher_id": team["team_id"], "pitches": 10}],
        }
        for team in teams
    ]
    next_games = [
        {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "opponent_id": (team["team_id"] % 30) + 1,
            "probable_pitcher_id": None,
            "probable_pitcher_name": None,
            "probable_recent_starts": [],
            "probable_days_rest": None,
            "is_rest_day_today": False,
            "schedule_date": "2026-07-23",
        }
        for team in teams
    ]
    dates = [f"2026-07-{day:02d}" for day in range(10, 24)]
    bullpen_usage = [
        {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "end_date": dates[-1],
            "dates": dates,
            "pitchers": [],
        }
        for team in teams
    ]
    points = [
        {
            "date": "2026-07-23",
            **team,
        }
        for team in teams
    ]
    dashboard = {
        "schema_version": SCHEMA_VERSION,
        "season": 2026,
        "data_commit": data_commit,
        "status": {"result": "complete", "current_games": 30},
        "teams": teams,
        "player_totals": player_totals,
        "team_pitcher_usage": usage,
        "recent_games": recent_games,
        "next_games": next_games,
        "bullpen_usage": bullpen_usage,
    }
    series = {
        "schema_version": SCHEMA_VERSION,
        "season": 2026,
        "data_commit": data_commit,
        "points": points,
        "complete_games": [],
    }
    return dashboard, series


def _write_dist(
    tmp_path: Path,
    dashboard: dict,
    series: dict,
    *,
    index: str = "<!doctype html><title>Dashboard</title>",
) -> Path:
    dist_dir = tmp_path / "dist"
    data_dir = dist_dir / "_file" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "dashboard.test.json").write_text(json.dumps(dashboard))
    (data_dir / "team-timeseries.test.json").write_text(json.dumps(series))
    (dist_dir / "index.html").write_text(index)
    return dist_dir


def test_verify_browser_payload_accepts_a_reconciled_build(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(tmp_path, dashboard, series)

    result = verify_browser_payload(
        dist_dir,
        expected_season=2026,
        expected_data_commit="data-sha",
    )

    assert result == {
        "teams": 30,
        "team_day_points": 30,
        "complete_games": 0,
        "player_totals": 30,
        "team_usage_windows": 30,
        "recent_games": 30,
        "next_games": 30,
        "bullpen_windows": 30,
        "current_games": 30,
    }


def test_verify_browser_payload_rejects_a_mismatched_data_revision(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(
        BrowserPayloadValidationError,
        match="data revision does not match",
    ):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="other-sha",
        )


@pytest.mark.parametrize(
    "status",
    [
        None,
        {},
        {"result": "complte"},
        {"result": "failed"},
    ],
)
def test_verify_browser_payload_rejects_an_invalid_snapshot_status(
    tmp_path: Path,
    status: object,
):
    dashboard, series = _valid_payloads()
    dashboard["status"] = status
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(
        BrowserPayloadValidationError,
        match="failed or invalid data snapshot",
    ):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


def test_verify_browser_payload_rejects_a_second_react_runtime(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(
        tmp_path,
        dashboard,
        series,
        index='<script src="/_node/react@19/index.js"></script>',
    )

    with pytest.raises(BrowserPayloadValidationError, match="second React runtime"):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


def test_verify_browser_payload_rejects_timeseries_drift(tmp_path: Path):
    dashboard, series = _valid_payloads()
    drifted = copy.deepcopy(series)
    drifted["points"][0]["total"] += 1
    dist_dir = _write_dist(tmp_path, dashboard, drifted)

    with pytest.raises(ValueError, match="timeseries total"):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )
