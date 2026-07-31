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
    starter_rest = [
        {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "as_of_date": "2026-07-23",
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
        "starter_rest": starter_rest,
    }
    series = {
        "schema_version": SCHEMA_VERSION,
        "season": 2026,
        "data_commit": data_commit,
        "points": points,
        "complete_games": [],
    }
    return dashboard, series


def _valid_player_history(dashboard: dict) -> dict:
    current_season = dashboard["season"]
    return {
        "schema_version": SCHEMA_VERSION,
        "season": current_season,
        "data_commit": dashboard["data_commit"],
        "historical_seasons": [current_season - 3, current_season - 2, current_season - 1],
        "players": [
            {
                "pitcher_id": leader["pitcher_id"],
                "pitcher_name": leader["pitcher_name"],
                "seasons": [
                    {
                        "season": historical_season,
                        "season_days": 183,
                        "total": 10,
                        "appearances": 1,
                        "points": [{"day": 30, "pitches": 10}],
                    }
                    for historical_season in range(current_season - 3, current_season)
                ] + [{
                    "season": current_season,
                    "season_days": 120,
                    "total": leader["total"],
                    "appearances": 1,
                    "points": [{"day": 120, "pitches": leader["total"]}],
                }],
            }
            for leader in dashboard["player_totals"]
        ],
    }


def _write_dist(
    tmp_path: Path,
    dashboard: dict,
    series: dict,
    *,
    player_history: dict | None = None,
    index: str = "<!doctype html><title>Dashboard</title>",
) -> Path:
    dist_dir = tmp_path / "dist"
    data_dir = dist_dir / "_file" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "dashboard.test.json").write_text(json.dumps(dashboard))
    (data_dir / "team-timeseries.test.json").write_text(json.dumps(series))
    history = player_history if player_history is not None else _valid_player_history(dashboard)
    (data_dir / "player-history.test.json").write_text(json.dumps(history))
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
        "player_history_players": 30,
        "team_usage_windows": 30,
        "recent_games": 30,
        "next_games": 30,
        "bullpen_windows": 30,
        "starter_rest_records": 30,
        "current_games": 30,
    }


def test_verify_browser_payload_requires_starter_rest_contract(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dashboard.pop("starter_rest")
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(
        BrowserPayloadValidationError,
        match="starter rest must be a list",
    ):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


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


@pytest.mark.parametrize(
    ("artifact", "field", "value", "message"),
    [
        ("dashboard", "schema_version", 999, "dashboard has an unsupported schema version"),
        ("team-timeseries", "schema_version", 999, "team-timeseries has an unsupported schema version"),
        ("player-history", "schema_version", 999, "player-history has an unsupported schema version"),
        ("dashboard", "season", 2025, "dashboard was built for the wrong season"),
        ("team-timeseries", "season", 2025, "team-timeseries was built for the wrong season"),
        ("player-history", "season", 2025, "player-history was built for the wrong season"),
        ("dashboard", "data_commit", "other", "dashboard data revision"),
        ("team-timeseries", "data_commit", "other", "team-timeseries data revision"),
        ("player-history", "data_commit", "other", "player-history data revision"),
    ],
)
def test_verify_browser_payload_checks_each_artifact_identity(
    tmp_path: Path,
    artifact: str,
    field: str,
    value: object,
    message: str,
):
    dashboard, series = _valid_payloads()
    history = _valid_player_history(dashboard)
    artifacts = {
        "dashboard": dashboard,
        "team-timeseries": series,
        "player-history": history,
    }
    artifacts[artifact][field] = value
    dist_dir = _write_dist(tmp_path, dashboard, series, player_history=history)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("team_pitcher_usage", "team pitcher usage must contain one record"),
        ("recent_games", "recent games must contain one record"),
        ("next_games", "next games must contain one record"),
        ("bullpen_usage", "bullpen usage must contain one record"),
        ("starter_rest", "starter rest must contain one record"),
    ],
)
def test_verify_browser_payload_requires_complete_team_sections(
    tmp_path: Path,
    key: str,
    message: str,
):
    dashboard, series = _valid_payloads()
    dashboard[key].pop()
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


def test_verify_browser_payload_allows_no_historical_next_games(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dashboard["next_games"] = []
    dist_dir = _write_dist(tmp_path, dashboard, series)

    result = verify_browser_payload(
        dist_dir,
        expected_season=2026,
        expected_data_commit="data-sha",
    )

    assert result["next_games"] == 0


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda dashboard: dashboard["teams"].__setitem__(
                1, {**dashboard["teams"][1], "team_id": 1},
            ),
            "invalid or duplicate ids",
            id="team-ids",
        ),
        pytest.param(
            lambda dashboard: dashboard["player_totals"].__setitem__(
                1, {**dashboard["player_totals"][1], "pitcher_id": 1},
            ),
            "invalid or duplicate pitchers",
            id="player-ids",
        ),
        pytest.param(
            lambda dashboard: dashboard["team_pitcher_usage"][0].__setitem__("total", None),
            "five lists of at most five pitchers",
            id="usage-list",
        ),
        pytest.param(
            lambda dashboard: dashboard["team_pitcher_usage"][0].__setitem__(
                "total", [{} for _ in range(6)],
            ),
            "five lists of at most five pitchers",
            id="usage-limit",
        ),
        pytest.param(
            lambda dashboard: dashboard["recent_games"][0].__setitem__("pitchers", []),
            "recent game has no pitcher workloads",
            id="recent-pitchers",
        ),
        pytest.param(
            lambda dashboard: dashboard["bullpen_usage"][0].__setitem__(
                "dates", dashboard["bullpen_usage"][0]["dates"][:-1],
            ),
            "14-day display contract",
            id="bullpen-dates",
        ),
        pytest.param(
            lambda dashboard: dashboard["bullpen_usage"][0].__setitem__(
                "pitchers", [{"pitches": [0 for _ in range(13)]}],
            ),
            "14-day display contract",
            id="bullpen-pitcher-window",
        ),
        pytest.param(
            lambda dashboard: dashboard["starter_rest"][0].__setitem__("pitchers", None),
            "starter-rest pitchers must be a list",
            id="starter-list",
        ),
    ],
)
def test_verify_browser_payload_rejects_display_contract_drift(
    tmp_path: Path,
    mutate,
    message: str,
):
    dashboard, series = _valid_payloads()
    mutate(dashboard)
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda history: history.__setitem__("historical_seasons", [2024, 2025]),
            "three completed prior seasons",
            id="historical-seasons",
        ),
        pytest.param(
            lambda history: history["players"].pop(),
            "do not match the current player leaders",
            id="leader-set",
        ),
        pytest.param(
            lambda history: history["players"][0]["seasons"][0].__setitem__("season", 2022),
            "invalid season sequence",
            id="season-sequence",
        ),
        pytest.param(
            lambda history: history["players"][0]["seasons"][-1].__setitem__("total", -1),
            "current total does not match",
            id="current-total",
        ),
    ],
)
def test_verify_browser_payload_rejects_player_history_drift(
    tmp_path: Path,
    mutate,
    message: str,
):
    dashboard, series = _valid_payloads()
    history = _valid_player_history(dashboard)
    mutate(history)
    dist_dir = _write_dist(tmp_path, dashboard, series, player_history=history)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("points", "team-timeseries points must be a list"),
        ("complete_games", "missing complete_games list"),
    ],
)
def test_verify_browser_payload_requires_timeseries_lists(
    tmp_path: Path,
    field: str,
    message: str,
):
    dashboard, series = _valid_payloads()
    series[field] = None
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


def test_verify_browser_payload_requires_compiled_index(tmp_path: Path):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(tmp_path, dashboard, series)
    (dist_dir / "index.html").unlink()

    with pytest.raises(BrowserPayloadValidationError, match="missing index.html"):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(
    ("filename", "replacement", "message"),
    [
        ("dashboard.test.json", "{not-json", "invalid dashboard JSON"),
        ("team-timeseries.test.json", "[]", "team-timeseries payload must be an object"),
    ],
)
def test_verify_browser_payload_rejects_invalid_compiled_json(
    tmp_path: Path,
    filename: str,
    replacement: str,
    message: str,
):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(tmp_path, dashboard, series)
    (dist_dir / "_file/data" / filename).write_text(replacement)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(("extra_copy", "found"), [(False, 0), (True, 2)])
def test_verify_browser_payload_requires_exactly_one_dashboard_payload(
    tmp_path: Path,
    extra_copy: bool,
    found: int,
):
    dashboard, series = _valid_payloads()
    dist_dir = _write_dist(tmp_path, dashboard, series)
    data_dir = dist_dir / "_file/data"
    dashboard_path = data_dir / "dashboard.test.json"
    if extra_copy:
        (data_dir / "dashboard.copy.json").write_text(dashboard_path.read_text())
    else:
        dashboard_path.unlink()

    with pytest.raises(
        BrowserPayloadValidationError,
        match=f"expected one dashboard payload, found {found}",
    ):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("teams", "expected 30 MLB teams"),
        ("player_totals", "exactly 30 player totals"),
    ],
)
def test_verify_browser_payload_requires_thirty_ranked_rows(
    tmp_path: Path,
    key: str,
    message: str,
):
    dashboard, series = _valid_payloads()
    dashboard[key].pop()
    dist_dir = _write_dist(tmp_path, dashboard, series)

    with pytest.raises(BrowserPayloadValidationError, match=message):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )


def test_verify_browser_payload_requires_player_history_list(tmp_path: Path):
    dashboard, series = _valid_payloads()
    history = _valid_player_history(dashboard)
    history["players"] = None
    dist_dir = _write_dist(tmp_path, dashboard, series, player_history=history)

    with pytest.raises(BrowserPayloadValidationError, match="players must be a list"):
        verify_browser_payload(
            dist_dir,
            expected_season=2026,
            expected_data_commit="data-sha",
        )
