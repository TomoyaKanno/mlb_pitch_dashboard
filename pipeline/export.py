from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .check import check_persisted_snapshot
from .schema import Snapshot
from .storage import load_snapshot


def aggregate_teams(snapshot: Snapshot) -> list[dict[str, Any]]:
    totals: dict[int, dict[str, Any]] = {}
    games: dict[int, set[int]] = defaultdict(set)
    latest_name: dict[int, tuple[str, str]] = {}

    for row in snapshot.appearances.values():
        team = totals.setdefault(
            row.team_id,
            {
                "team_id": row.team_id,
                "team_name": row.team_name,
                "total": 0,
                "official_sp": 0,
                "official_rp": 0,
                "adjusted_sp": 0,
                "adjusted_rp": 0,
                "bulk_to_sp": 0,
                "opener_to_rp": 0,
                "review_count": 0,
            },
        )
        previous_name = latest_name.get(row.team_id)
        if previous_name is None or row.game_date >= previous_name[0]:
            latest_name[row.team_id] = (row.game_date, row.team_name)
            team["team_name"] = row.team_name

        games[row.team_id].add(row.game_pk)
        team["total"] += row.pitches
        team["official_sp" if row.official_started else "official_rp"] += row.pitches
        team["adjusted_sp" if row.adjusted_role == "SP" else "adjusted_rp"] += row.pitches
        if not row.official_started and row.adjusted_role == "SP":
            team["bulk_to_sp"] += row.pitches
        if row.official_started and row.adjusted_role == "RP":
            team["opener_to_rp"] += row.pitches
        team["review_count"] += int(row.needs_review)

    result: list[dict[str, Any]] = []
    for team_id, team in totals.items():
        team["games"] = len(games[team_id])
        if team["total"] != team["official_sp"] + team["official_rp"]:
            raise ValueError(f"official role totals do not balance for team {team_id}")
        if team["total"] != team["adjusted_sp"] + team["adjusted_rp"]:
            raise ValueError(f"adjusted role totals do not balance for team {team_id}")
        result.append(team)
    return sorted(result, key=lambda team: (-team["total"], team["team_name"]))


def export_dashboard(data_dir: Path, season: int) -> dict[str, Any]:
    verified = check_persisted_snapshot(data_dir, season)
    snapshot = load_snapshot(data_dir, season)
    manifest_path = data_dir / "seasons" / str(season) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    teams = aggregate_teams(snapshot)
    return {
        "schema_version": 1,
        "season": season,
        "generated_at": manifest["generated_at"],
        "code_commit": os.getenv("GITHUB_SHA"),
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
        "teams": teams,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export browser-ready MLB dashboard data")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    json.dump(export_dashboard(args.data_dir, args.season), fp=sys.stdout, separators=(",", ":"))
    print()


if __name__ == "__main__":
    main()
