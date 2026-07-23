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


def aggregate_pitchers(snapshot: Snapshot, *, limit: int = 30) -> list[dict[str, Any]]:
    """Top individual season pitch totals, labeled with the current roster team.

    Every persisted appearance contributes to one MLB pitcher id, including
    appearances before a trade. The current-season roster snapshot supplies the
    displayed team and name when available; otherwise the latest appearance is
    the stable fallback for historical snapshots and departed players.
    """
    totals: dict[int, int] = defaultdict(int)
    latest: dict[int, tuple[str, int, int, str, str]] = {}

    for row in snapshot.appearances.values():
        totals[row.pitcher_id] += row.pitches
        candidate = (
            row.game_date,
            row.game_pk,
            row.team_id,
            row.team_name,
            row.pitcher_name,
        )
        if row.pitcher_id not in latest or candidate[:2] >= latest[row.pitcher_id][:2]:
            latest[row.pitcher_id] = candidate

    current_roster = {row.pitcher_id: row for row in snapshot.roster_pitchers.values()}
    result: list[dict[str, Any]] = []
    for pitcher_id, total in totals.items():
        roster = current_roster.get(pitcher_id)
        if roster is not None:
            team_id = roster.team_id
            team_name = roster.team_name
            pitcher_name = roster.pitcher_name
        else:
            _game_date, _game_pk, team_id, team_name, pitcher_name = latest[pitcher_id]
        result.append(
            {
                "pitcher_id": pitcher_id,
                "pitcher_name": pitcher_name,
                "team_id": team_id,
                "team_name": team_name,
                "total": total,
            }
        )

    return sorted(
        result,
        key=lambda row: (-row["total"], row["pitcher_name"], row["pitcher_id"]),
    )[:limit]


def aggregate_team_pitcher_usage(
    snapshot: Snapshot,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Top per-team pitcher workloads for every season-leader role framing.

    Roles remain appearance-level facts. A swingman can therefore rank in both
    SP and RP lists, with official and role-adjusted lists reflecting their
    respective classifications instead of assigning one permanent label.
    """
    by_pitcher: dict[tuple[int, int], dict[str, Any]] = {}
    latest_team_name: dict[int, tuple[str, int, str]] = {}

    for row in snapshot.appearances.values():
        key = (row.team_id, row.pitcher_id)
        pitcher = by_pitcher.setdefault(
            key,
            {
                "pitcher_id": row.pitcher_id,
                "pitcher_name": row.pitcher_name,
                **_empty_metrics(),
            },
        )
        _accumulate_appearance(pitcher, row)
        latest = latest_team_name.get(row.team_id)
        candidate = (row.game_date, row.game_pk, row.team_name)
        if latest is None or candidate[:2] >= latest[:2]:
            latest_team_name[row.team_id] = candidate

    by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (team_id, _pitcher_id), pitcher in by_pitcher.items():
        _assert_role_balance(f"pitcher {pitcher['pitcher_id']} on team {team_id}", pitcher)
        by_team[team_id].append(pitcher)

    result: list[dict[str, Any]] = []
    for team_id, pitchers in by_team.items():
        team_name = latest_team_name[team_id][2]
        leaderboards = {
            key: sorted(
                (pitcher for pitcher in pitchers if pitcher[key] > 0),
                key=lambda pitcher: (-pitcher[key], pitcher["pitcher_name"], pitcher["pitcher_id"]),
            )[:limit]
            for key in ("total", "official_sp", "official_rp", "adjusted_sp", "adjusted_rp")
        }
        result.append({"team_id": team_id, "team_name": team_name, **leaderboards})

    return sorted(result, key=lambda row: row["team_name"])


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


def _appearances_by_game_team(snapshot: Snapshot) -> dict[tuple[int, int], list[Any]]:
    grouped: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for row in snapshot.appearances.values():
        grouped[(row.game_pk, row.team_id)].append(row)
    return grouped


def _latest_team_games(
    snapshot: Snapshot,
    by_game_team: dict[tuple[int, int], list[Any]],
) -> dict[int, tuple[Any, list[Any]]]:
    latest: dict[int, tuple[Any, list[Any]]] = {}
    for (game_pk, team_id), rows in by_game_team.items():
        game = snapshot.games.get(game_pk)
        if game is None:
            continue
        previous = latest.get(team_id)
        if previous is None or (
            game.game_date, game.game_datetime or "", game.game_pk,
        ) > (
            previous[0].game_date,
            previous[0].game_datetime or "",
            previous[0].game_pk,
        ):
            latest[team_id] = (game, rows)
    return latest


def aggregate_complete_games(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Team-games with zero official RP pitches (true complete games).

    Must be game-grain, not calendar-day: a doubleheader can pair a CG with a
    bullpen game, so the day total still has official_rp > 0.
    """
    by_game_team = _appearances_by_game_team(snapshot)

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
    by_game_team = _appearances_by_game_team(snapshot)
    latest = _latest_team_games(snapshot, by_game_team)

    result: list[dict[str, Any]] = []
    for team_id, (game, rows) in latest.items():
        ordered = sorted(rows, key=lambda row: (row.appearance_order, row.pitcher_id))
        matchup = {}
        if (
            game.away_team_id is not None
            and game.away_team_name
            and game.home_team_id is not None
            and game.home_team_name
        ):
            matchup = {
                "away_team_id": game.away_team_id,
                "away_team_name": game.away_team_name,
                "home_team_id": game.home_team_id,
                "home_team_name": game.home_team_name,
            }
        result.append(
            {
                "team_id": team_id,
                "team_name": ordered[0].team_name,
                "game_pk": game.game_pk,
                "date": game.game_date,
                "game_datetime": game.game_datetime,
                **matchup,
                "pitchers": [
                    {
                        "pitcher_id": row.pitcher_id,
                        "pitcher_name": row.pitcher_name,
                        "pitches": row.pitches,
                        "official_started": row.official_started,
                        "appearance_order": row.appearance_order,
                        "jersey_number": (
                            snapshot.roster_pitchers[(team_id, row.pitcher_id)].jersey_number
                            if (team_id, row.pitcher_id) in snapshot.roster_pitchers
                            else None
                        ),
                    }
                    for row in ordered
                ],
            }
        )
    return sorted(result, key=lambda row: row["team_name"])


def _roster_availability(status_code: str) -> str | None:
    """Map MLB roster status codes to compact dashboard badges."""
    if status_code == "A":
        return None
    if status_code in {"D7", "D10", "D15", "D60"}:
        return "IL"
    if status_code == "RM":
        return "Minors"
    return status_code


def aggregate_bullpen_usage(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Fourteen calendar days of reliever pitch counts for each team.

    The window ends with the team's latest completed game. Doubleheaders add
    both games into the same calendar-day cell, which reflects total workload.
    Depth-chart bullpen arms (``RP`` / ``CP``) are included even with zero
    pitches so unused call-ups remain visible. IL and Minors arms are kept only
    when they recorded pitches in the window. Roster availability badges come
    from the persisted depth-chart / 40-man snapshot when present.
    """
    by_game_team = _appearances_by_game_team(snapshot)
    latest = _latest_team_games(snapshot, by_game_team)
    roster_by_team: dict[int, list[Any]] = defaultdict(list)
    for row in snapshot.roster_pitchers.values():
        roster_by_team[row.team_id].append(row)

    result: list[dict[str, Any]] = []
    for team_id, (latest_game, latest_rows) in latest.items():
        end_date = date.fromisoformat(latest_game.game_date)
        dates = [
            (end_date - timedelta(days=13 - offset)).isoformat()
            for offset in range(14)
        ]
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

        roster_rows = {
            row.pitcher_id: row
            for row in roster_by_team.get(team_id, [])
        }
        pitcher_ids = set(pitcher_names)
        for row in roster_rows.values():
            if row.depth_role in {"RP", "CP"}:
                pitcher_ids.add(row.pitcher_id)
                pitcher_names.setdefault(row.pitcher_id, row.pitcher_name)

        pitchers: list[dict[str, Any]] = []
        for pitcher_id in pitcher_ids:
            roster = roster_rows.get(pitcher_id)
            pitches = [pitch_counts[(pitcher_id, offset)] for offset in range(14)]
            on_depth_chart = roster is not None and roster.depth_role in {"RP", "CP"}
            availability = (
                _roster_availability(roster.status_code) if roster is not None else None
            )
            # Unavailable arms only stay visible when they actually worked in-window:
            # that preserves "what happened to that guy" without listing idle IL/minors.
            if availability in {"IL", "Minors"} and sum(pitches) == 0:
                continue
            pitchers.append(
                {
                    "pitcher_id": pitcher_id,
                    "pitcher_name": (
                        roster.pitcher_name if roster is not None else pitcher_names[pitcher_id]
                    ),
                    "pitches": pitches,
                    "depth_role": roster.depth_role if on_depth_chart else None,
                    "depth_order": roster.depth_order if on_depth_chart else None,
                    "on_depth_chart": on_depth_chart,
                    "availability": availability,
                    "status_description": (
                        roster.status_description if roster is not None else None
                    ),
                }
            )

        pitchers.sort(
            key=lambda row: (
                0 if row["on_depth_chart"] else 1,
                row["depth_order"] if row["depth_order"] is not None else 10**9,
                -sum(row["pitches"]),
                row["pitcher_name"],
            )
        )
        result.append(
            {
                "team_id": team_id,
                "team_name": latest_rows[0].team_name,
                "end_date": latest_game.game_date,
                "dates": dates,
                "pitchers": pitchers,
            }
        )

    return sorted(result, key=lambda row: row["team_name"])


def _probable_recent_starts(
    snapshot: Snapshot,
    pitcher_id: int,
    next_game_date: str,
    *,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], int | None]:
    """Most recent official starts for a probable pitcher, plus days of rest.

    Days of rest use the baseball convention: calendar days between the most
    recent official start and the upcoming game, minus one. Role-adjusted
    classification is ignored — only MLB ``gamesStarted`` appearances count.
    """
    starts: list[tuple[str, int, int, str | None]] = []
    for row in snapshot.appearances.values():
        if row.pitcher_id != pitcher_id or not row.official_started:
            continue
        game = snapshot.games.get(row.game_pk)
        opponent_name = None
        if game is not None:
            if game.away_team_id == row.team_id:
                opponent_name = game.home_team_name
            elif game.home_team_id == row.team_id:
                opponent_name = game.away_team_name
        starts.append((row.game_date, row.game_pk, row.pitches, opponent_name))

    starts.sort(key=lambda item: (item[0], item[1]), reverse=True)
    recent = [
        {
            "date": game_date,
            "game_pk": game_pk,
            "pitches": pitches,
            "opponent_name": opponent_name,
        }
        for game_date, game_pk, pitches, opponent_name in starts[:limit]
    ]
    if not recent:
        return [], None

    last_date = date.fromisoformat(recent[0]["date"])
    next_date = date.fromisoformat(next_game_date)
    days_rest = max(0, (next_date - last_date).days - 1)
    return recent, days_rest


def aggregate_next_games(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Upcoming opponent and optional MLB probable starter for each team.

    When MLB lists a probable starter, include that pitcher's most recent
    official starts (up to three) and days of rest before the upcoming game.
    """
    result: list[dict[str, Any]] = []
    for row in sorted(snapshot.next_games.values(), key=lambda item: item.team_name):
        recent_starts: list[dict[str, Any]] = []
        days_rest: int | None = None
        if row.probable_pitcher_id is not None:
            recent_starts, days_rest = _probable_recent_starts(
                snapshot, row.probable_pitcher_id, row.game_date,
            )
            roster = snapshot.roster_pitchers.get((row.team_id, row.probable_pitcher_id))
            probable_jersey = roster.jersey_number if roster is not None else None
        else:
            probable_jersey = None
        result.append(
            {
                "team_id": row.team_id,
                "team_name": row.team_name,
                "game_pk": row.game_pk,
                "date": row.game_date,
                "game_datetime": row.game_datetime,
                "opponent_id": row.opponent_id,
                "opponent_name": row.opponent_name,
                "is_home": row.is_home,
                "probable_pitcher_id": row.probable_pitcher_id,
                "probable_pitcher_name": row.probable_pitcher_name,
                "probable_jersey_number": probable_jersey,
                "probable_recent_starts": recent_starts,
                "probable_days_rest": days_rest,
                "is_rest_day_today": row.is_rest_day_today,
                "schedule_date": row.schedule_date,
            }
        )
    return result


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
    return {
        **meta,
        "teams": teams,
        "player_totals": aggregate_pitchers(snapshot),
        "team_pitcher_usage": aggregate_team_pitcher_usage(snapshot),
        "recent_games": aggregate_recent_games(snapshot),
        "next_games": aggregate_next_games(snapshot),
        "bullpen_usage": aggregate_bullpen_usage(snapshot),
    }


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
