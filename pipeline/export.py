from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .check import check_persisted_snapshot
from .schema import Snapshot
from .storage import load_snapshot

METRIC_KEYS = (
    "total",
    "official_sp",
    "official_rp",
    "adjusted_sp",
    "adjusted_rp",
    "bulk_to_sp",
    "opener_to_rp",
    "review_count",
)


def _empty_metrics() -> dict[str, int]:
    return {key: 0 for key in METRIC_KEYS}


def _accumulate_appearance(bucket: dict[str, Any], row: Any) -> None:
    bucket["total"] += row.pitches
    bucket["official_sp" if row.official_started else "official_rp"] += row.pitches
    bucket["adjusted_sp" if row.adjusted_role == "SP" else "adjusted_rp"] += row.pitches
    if not row.official_started and row.adjusted_role == "SP":
        bucket["bulk_to_sp"] += row.pitches
    if row.official_started and row.adjusted_role == "RP":
        bucket["opener_to_rp"] += row.pitches
    bucket["review_count"] += int(row.needs_review)


def _assert_role_balance(label: str, bucket: dict[str, Any]) -> None:
    if bucket["total"] != bucket["official_sp"] + bucket["official_rp"]:
        raise ValueError(f"official role totals do not balance for {label}")
    if bucket["total"] != bucket["adjusted_sp"] + bucket["adjusted_rp"]:
        raise ValueError(f"adjusted role totals do not balance for {label}")


def aggregate_teams(snapshot: Snapshot) -> list[dict[str, Any]]:
    totals: dict[int, dict[str, Any]] = {}
    games: dict[int, set[int]] = defaultdict(set)
    latest_name: dict[int, tuple[str, str]] = {}

    for row in snapshot.appearances.values():
        team = totals.setdefault(
            row.team_id,
            {"team_id": row.team_id, "team_name": row.team_name, **_empty_metrics()},
        )
        previous_name = latest_name.get(row.team_id)
        if previous_name is None or row.game_date >= previous_name[0]:
            latest_name[row.team_id] = (row.game_date, row.team_name)
            team["team_name"] = row.team_name

        games[row.team_id].add(row.game_pk)
        _accumulate_appearance(team, row)

    result: list[dict[str, Any]] = []
    for team_id, team in totals.items():
        team["games"] = len(games[team_id])
        _assert_role_balance(f"team {team_id}", team)
        result.append(team)
    return sorted(result, key=lambda team: (-team["total"], team["team_name"]))


def aggregate_team_timeseries(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Daily team increments: one point per (game_date, team_id) with activity.

    Points are additive facts. Summing a metric across dates for a team equals
    that team's season total from aggregate_teams. Clients cumsum for charts.
    """
    points: dict[tuple[str, int], dict[str, Any]] = {}
    games: dict[tuple[str, int], set[int]] = defaultdict(set)
    latest_name: dict[tuple[str, int], str] = {}

    for row in snapshot.appearances.values():
        key = (row.game_date, row.team_id)
        point = points.setdefault(
            key,
            {
                "date": row.game_date,
                "team_id": row.team_id,
                "team_name": row.team_name,
                **_empty_metrics(),
            },
        )
        latest_name[key] = row.team_name
        point["team_name"] = row.team_name
        games[key].add(row.game_pk)
        _accumulate_appearance(point, row)

    result: list[dict[str, Any]] = []
    for key, point in points.items():
        point["games"] = len(games[key])
        point["team_name"] = latest_name[key]
        _assert_role_balance(f"team {point['team_id']} on {point['date']}", point)
        result.append(point)
    return sorted(result, key=lambda point: (point["date"], point["team_id"]))


def aggregate_complete_games(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Team-games with zero official RP pitches (true complete games).

    Must be game-grain, not calendar-day: a doubleheader can pair a CG with a
    bullpen game, so the day total still has official_rp > 0.
    """
    by_game_team: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for row in snapshot.appearances.values():
        by_game_team[(row.game_pk, row.team_id)].append(row)

    result: list[dict[str, Any]] = []
    for (game_pk, team_id), rows in by_game_team.items():
        rows = sorted(rows, key=lambda item: item.appearance_order)
        total = sum(row.pitches for row in rows)
        official_rp = sum(row.pitches for row in rows if not row.official_started)
        if total <= 0 or official_rp > 0:
            continue
        pitcher_ids = {row.pitcher_id for row in rows}
        if len(pitcher_ids) != 1:
            continue
        pitcher = rows[0]
        result.append(
            {
                "date": pitcher.game_date,
                "game_pk": game_pk,
                "team_id": team_id,
                "team_name": pitcher.team_name,
                "pitches": total,
                "pitcher_id": pitcher.pitcher_id,
                "pitcher_name": pitcher.pitcher_name,
            }
        )
    return sorted(result, key=lambda row: (row["date"], row["team_id"], row["game_pk"]))


def aggregate_recent_games(snapshot: Snapshot) -> list[dict[str, Any]]:
    """One latest completed team-game with its individual pitcher pitch counts.

    MLB scheduled game time makes same-day doubleheaders deterministic. Legacy
    snapshots without that optional timestamp fall back to game_pk until their
    next normal refresh rewrites the game records.
    """
    by_game_team: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for row in snapshot.appearances.values():
        by_game_team[(row.game_pk, row.team_id)].append(row)

    latest: dict[int, tuple[Any, list[Any]]] = {}
    for (game_pk, team_id), rows in by_game_team.items():
        game = snapshot.games.get(game_pk)
        if game is None:
            continue
        previous = latest.get(team_id)
        if previous is None or (
            game.game_date, game.game_datetime or "", game.game_pk,
        ) > (
            previous[0].game_date, previous[0].game_datetime or "", previous[0].game_pk,
        ):
            latest[team_id] = (game, rows)

    result: list[dict[str, Any]] = []
    for team_id, (game, rows) in latest.items():
        ordered = sorted(rows, key=lambda row: (row.appearance_order, row.pitcher_id))
        result.append(
            {
                "team_id": team_id,
                "team_name": ordered[0].team_name,
                "game_pk": game.game_pk,
                "date": game.game_date,
                "game_datetime": game.game_datetime,
                "pitchers": [
                    {
                        "pitcher_id": row.pitcher_id,
                        "pitcher_name": row.pitcher_name,
                        "pitches": row.pitches,
                        "official_started": row.official_started,
                        "appearance_order": row.appearance_order,
                    }
                    for row in ordered
                ],
            }
        )
    return sorted(result, key=lambda row: row["team_name"])


def aggregate_bullpen_usage(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Fourteen calendar days of reliever pitch counts for each team.

    The window ends with the team's latest completed game. Doubleheaders add
    both games into the same calendar-day cell, which reflects total workload.
    """
    by_game_team: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for row in snapshot.appearances.values():
        by_game_team[(row.game_pk, row.team_id)].append(row)

    latest: dict[int, tuple[Any, list[Any]]] = {}
    for (game_pk, team_id), rows in by_game_team.items():
        game = snapshot.games.get(game_pk)
        if game is None:
            continue
        previous = latest.get(team_id)
        if previous is None or (
            game.game_date, game.game_datetime or "", game.game_pk,
        ) > (
            previous[0].game_date, previous[0].game_datetime or "", previous[0].game_pk,
        ):
            latest[team_id] = (game, rows)

    result: list[dict[str, Any]] = []
    for team_id, (latest_game, latest_rows) in latest.items():
        end_date = date.fromisoformat(latest_game.game_date)
        dates = [(end_date - timedelta(days=13 - offset)).isoformat() for offset in range(14)]
        date_indexes = {day: index for index, day in enumerate(dates)}
        pitch_counts: dict[tuple[int, int], int] = defaultdict(int)
        pitcher_names: dict[int, str] = {}
        for (game_pk, game_team_id), rows in by_game_team.items():
            if game_team_id != team_id:
                continue
            game = snapshot.games.get(game_pk)
            if game is None or game.game_date not in date_indexes:
                continue
            for row in rows:
                if row.official_started:
                    continue
                pitch_counts[(row.pitcher_id, date_indexes[game.game_date])] += row.pitches
                pitcher_names[row.pitcher_id] = row.pitcher_name

        pitchers = [
            {"pitcher_id": pitcher_id, "pitcher_name": pitcher_names[pitcher_id],
             "pitches": [pitch_counts[(pitcher_id, offset)] for offset in range(14)]}
            for pitcher_id in pitcher_names
        ]
        pitchers.sort(key=lambda row: (-sum(row["pitches"]), row["pitcher_name"]))
        result.append({"team_id": team_id, "team_name": latest_rows[0].team_name,
                       "end_date": latest_game.game_date, "dates": dates, "pitchers": pitchers})

    return sorted(result, key=lambda row: row["team_name"])

def reconcile_team_timeseries(
    teams: list[dict[str, Any]],
    points: list[dict[str, Any]],
) -> None:
    """Require daily increments to reconstruct season team totals exactly."""
    by_team: dict[int, dict[str, int]] = defaultdict(_empty_metrics)
    games: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}

    for point in points:
        team_id = int(point["team_id"])
        names[team_id] = str(point["team_name"])
        games[team_id] += int(point["games"])
        for key in METRIC_KEYS:
            by_team[team_id][key] += int(point[key])

    team_ids = {int(team["team_id"]) for team in teams}
    point_ids = set(by_team)
    if team_ids != point_ids:
        raise ValueError(
            "team timeseries team_id set does not match season teams: "
            f"only_teams={sorted(team_ids - point_ids)} "
            f"only_series={sorted(point_ids - team_ids)}"
        )

    for team in teams:
        team_id = int(team["team_id"])
        summed = by_team[team_id]
        for key in METRIC_KEYS:
            if int(team[key]) != summed[key]:
                raise ValueError(
                    f"timeseries {key} for team {team_id} sums to {summed[key]}, "
                    f"season total is {team[key]}"
                )
        if int(team["games"]) != games[team_id]:
            raise ValueError(
                f"timeseries games for team {team_id} sum to {games[team_id]}, "
                f"season total is {team['games']}"
            )


def _export_common(data_dir: Path, season: int) -> tuple[Snapshot, dict[str, Any], dict[str, Any]]:
    verified = check_persisted_snapshot(data_dir, season)
    snapshot = load_snapshot(data_dir, season)
    manifest_path = data_dir / "seasons" / str(season) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    meta = {
        "schema_version": 1,
        "season": season,
        "generated_at": manifest["generated_at"],
        "code_commit": os.getenv("DASHBOARD_CODE_SHA") or os.getenv("GITHUB_SHA"),
        "data_commit": os.getenv("DASHBOARD_DATA_SHA"),
        "status": {
            "result": manifest["result"],
            "api_calls": manifest["api_calls"],
            "games_requested": manifest["games_requested"],
            "games_fetched": manifest["games_fetched"],
            "games_failed": manifest["games_failed"],
            "scheduled_games": verified["scheduled_games"],
            "current_games": verified["current_games"],
            "stale_games": verified["stale_games"],
            "missing_games": verified["missing_games"],
        },
    }
    return snapshot, verified, meta


def export_dashboard(data_dir: Path, season: int) -> dict[str, Any]:
    snapshot, _verified, meta = _export_common(data_dir, season)
    teams = aggregate_teams(snapshot)
    return {**meta, "teams": teams, "recent_games": aggregate_recent_games(snapshot)}


def export_team_timeseries(data_dir: Path, season: int) -> dict[str, Any]:
    snapshot, _verified, meta = _export_common(data_dir, season)
    teams = aggregate_teams(snapshot)
    points = aggregate_team_timeseries(snapshot)
    reconcile_team_timeseries(teams, points)
    return {
        **meta,
        "points": points,
        "complete_games": aggregate_complete_games(snapshot),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export browser-ready MLB dashboard data")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument(
        "--kind",
        choices=("dashboard", "team-timeseries"),
        default="dashboard",
        help="dashboard = season team totals; team-timeseries = daily increments + complete games",
    )
    args = parser.parse_args()
    if args.kind == "team-timeseries":
        payload = export_team_timeseries(args.data_dir, args.season)
    else:
        payload = export_dashboard(args.data_dir, args.season)
    json.dump(payload, fp=sys.stdout, separators=(",", ":"))
    print()


if __name__ == "__main__":
    main()
