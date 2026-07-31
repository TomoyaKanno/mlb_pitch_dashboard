from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import SCHEMA_VERSION
from .storage import load_snapshot
from .validation import SnapshotValidationError, validate_snapshot


def check_persisted_snapshot(data_dir: Path, season: int) -> dict[str, Any]:
    """Reload and independently verify a serialized season snapshot."""
    root = data_dir / "seasons" / str(season)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise SnapshotValidationError(f"missing manifest: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise SnapshotValidationError(f"invalid manifest: {exc}") from exc
    if int(manifest.get("schema_version", 0)) != SCHEMA_VERSION:
        raise SnapshotValidationError("manifest has an unsupported schema version")
    if int(manifest.get("season", 0)) != season:
        raise SnapshotValidationError("manifest belongs to another season")

    actual_files = {
        path.relative_to(root).as_posix()
        for directory in (root / "games", root / "appearances")
        for path in directory.glob("*.jsonl")
    }
    for filename in ("fetch-state.json", "next-games.json", "roster-pitchers.json"):
        if (root / filename).is_file():
            actual_files.add(filename)

    declared_files = manifest.get("files")
    if not isinstance(declared_files, dict):
        raise SnapshotValidationError("manifest files must be an object")
    if set(declared_files) != actual_files:
        missing = sorted(set(declared_files) - actual_files)
        unexpected = sorted(actual_files - set(declared_files))
        raise SnapshotValidationError(
            f"manifest file set mismatch; missing={missing}, unexpected={unexpected}"
        )

    for relative, expected in declared_files.items():
        content = (root / relative).read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if int(expected.get("bytes", -1)) != len(content):
            raise SnapshotValidationError(f"byte count mismatch for {relative}")
        if expected.get("sha256") != actual_hash:
            raise SnapshotValidationError(f"SHA-256 mismatch for {relative}")

    snapshot = load_snapshot(data_dir, season)
    validate_snapshot(snapshot)
    scheduled = set(snapshot.games)
    data_games = {row.game_pk for row in snapshot.appearances.values()}
    current = {
        game_pk
        for game_pk, state in snapshot.fetch_state.items()
        if game_pk in scheduled and state.fetch_status == "success" and game_pk in data_games
    }
    stale = {
        game_pk
        for game_pk, state in snapshot.fetch_state.items()
        if game_pk in scheduled and state.fetch_status == "failed" and game_pk in data_games
    }
    coverage = {
        "scheduled_games": len(scheduled),
        "current_games": len(current),
        "stale_games": len(stale),
        "missing_games": len(scheduled - current - stale),
    }
    for key, actual in coverage.items():
        if int(manifest.get(key, -1)) != actual:
            raise SnapshotValidationError(
                f"manifest {key} is {manifest.get(key)!r}, but snapshot contains {actual}"
            )
    return {
        "season": season,
        "games": len(snapshot.games),
        "appearances": len(snapshot.appearances),
        **coverage,
        "files": len(actual_files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a persisted MLB season snapshot")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    result = check_persisted_snapshot(args.data_dir, args.season)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
