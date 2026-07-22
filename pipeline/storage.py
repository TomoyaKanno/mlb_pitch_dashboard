from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, TypeVar

from .schema import (
    AppearanceRecord,
    FetchStateRecord,
    GameRecord,
    NextGameRecord,
    RosterPitcherRecord,
    SCHEMA_VERSION,
    Snapshot,
)


T = TypeVar("T")


def _read_jsonl(path: Path, parser: Callable[[dict[str, Any]], T]) -> list[T]:
    rows: list[T] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if line.strip():
            try:
                rows.append(parser(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid record in {path}:{line_number}: {exc}") from exc
    return rows


def load_snapshot(data_dir: Path, season: int) -> Snapshot:
    root = data_dir / "seasons" / str(season)
    snapshot = Snapshot(season=season)
    if not root.exists():
        return snapshot

    for path in sorted((root / "games").glob("*.jsonl")):
        for row in _read_jsonl(path, GameRecord.from_dict):
            if row.game_pk in snapshot.games:
                raise ValueError(f"duplicate game {row.game_pk}")
            snapshot.games[row.game_pk] = row

    for path in sorted((root / "appearances").glob("*.jsonl")):
        for row in _read_jsonl(path, AppearanceRecord.from_dict):
            if row.key in snapshot.appearances:
                raise ValueError(f"duplicate appearance {row.key}")
            snapshot.appearances[row.key] = row

    state_path = root / "fetch-state.json"
    if state_path.exists():
        payload = json.loads(state_path.read_text())
        if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version in {state_path}")
        if int(payload["season"]) != season:
            raise ValueError(f"fetch state in {state_path} belongs to another season")
        for value in payload.get("games", []):
            row = FetchStateRecord.from_dict(value)
            if row.game_pk in snapshot.fetch_state:
                raise ValueError(f"duplicate fetch state {row.game_pk}")
            snapshot.fetch_state[row.game_pk] = row

    next_games_path = root / "next-games.json"
    if next_games_path.exists():
        payload = json.loads(next_games_path.read_text())
        if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version in {next_games_path}")
        if int(payload["season"]) != season:
            raise ValueError(f"next-game data in {next_games_path} belongs to another season")
        for value in payload.get("games", []):
            row = NextGameRecord.from_dict(value)
            if row.team_id in snapshot.next_games:
                raise ValueError(f"duplicate next game for team {row.team_id}")
            snapshot.next_games[row.team_id] = row

    roster_path = root / "roster-pitchers.json"
    if roster_path.exists():
        payload = json.loads(roster_path.read_text())
        if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version in {roster_path}")
        if int(payload["season"]) != season:
            raise ValueError(f"roster data in {roster_path} belongs to another season")
        for value in payload.get("pitchers", []):
            row = RosterPitcherRecord.from_dict(value)
            if row.key in snapshot.roster_pitchers:
                raise ValueError(
                    f"duplicate roster pitcher {row.pitcher_id} for team {row.team_id}"
                )
            snapshot.roster_pitchers[row.key] = row
    return snapshot


def _jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def write_snapshot(snapshot: Snapshot, refresh: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    root = data_dir / "seasons" / str(snapshot.season)
    partitions: dict[str, str] = {}
    games_by_month: dict[str, list[GameRecord]] = defaultdict(list)
    appearances_by_month: dict[str, list[AppearanceRecord]] = defaultdict(list)

    for row in snapshot.games.values():
        games_by_month[row.game_date[:7]].append(row)
    for row in snapshot.appearances.values():
        appearances_by_month[row.game_date[:7]].append(row)

    for month, rows in games_by_month.items():
        path = f"games/{month}.jsonl"
        partitions[path] = _jsonl(
            [row.to_dict() for row in sorted(rows, key=lambda item: (item.game_date, item.game_pk))]
        )
    for month, rows in appearances_by_month.items():
        path = f"appearances/{month}.jsonl"
        partitions[path] = _jsonl(
            [
                row.to_dict()
                for row in sorted(
                    rows,
                    key=lambda item: (item.game_date, item.game_pk, item.team_id, item.appearance_order),
                )
            ]
        )

    state_payload = {
        "schema_version": SCHEMA_VERSION,
        "season": snapshot.season,
        "games": [
            row.to_dict() for row in sorted(snapshot.fetch_state.values(), key=lambda item: item.game_pk)
        ],
    }
    partitions["fetch-state.json"] = json.dumps(state_payload, indent=2, sort_keys=True) + "\n"
    next_games_payload = {
        "schema_version": SCHEMA_VERSION,
        "season": snapshot.season,
        "games": [
            row.to_dict() for row in sorted(snapshot.next_games.values(), key=lambda item: item.team_name)
        ],
    }
    partitions["next-games.json"] = json.dumps(next_games_payload, indent=2, sort_keys=True) + "\n"
    roster_payload = {
        "schema_version": SCHEMA_VERSION,
        "season": snapshot.season,
        "pitchers": [
            row.to_dict()
            for row in sorted(
                snapshot.roster_pitchers.values(),
                key=lambda item: (
                    item.team_name,
                    item.depth_order is None,
                    item.depth_order if item.depth_order is not None else 10**9,
                    item.pitcher_name,
                ),
            )
        ],
    }
    partitions["roster-pitchers.json"] = json.dumps(roster_payload, indent=2, sort_keys=True) + "\n"

    expected = {root / relative for relative in partitions}
    for directory in (root / "games", root / "appearances"):
        if directory.exists():
            for old_path in directory.glob("*.jsonl"):
                if old_path not in expected:
                    old_path.unlink()
    for relative, content in partitions.items():
        _atomic_write(root / relative, content)

    files = {
        relative: {
            "bytes": len(content.encode()),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        }
        for relative, content in sorted(partitions.items())
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "season": snapshot.season,
        **refresh,
        "files": files,
    }
    _atomic_write(root / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
