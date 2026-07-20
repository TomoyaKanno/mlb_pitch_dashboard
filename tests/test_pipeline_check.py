from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.check import check_persisted_snapshot
from pipeline.schema import AppearanceRecord, FetchStateRecord, GameRecord, Snapshot
from pipeline.storage import write_snapshot
from pipeline.validation import SnapshotValidationError


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc).isoformat()


def valid_snapshot() -> Snapshot:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = GameRecord(1, "2026-07-19", 2026, "Final")
    snapshot.fetch_state[1] = FetchStateRecord(1, "success", NOW, NOW, None, 1)
    away = AppearanceRecord(
        1, "2026-07-19", 2026, 100, "Away", 11, "Away Starter", 88,
        True, 0, "SP", "official starter",
    )
    home = AppearanceRecord(
        1, "2026-07-19", 2026, 200, "Home", 21, "Home Starter", 91,
        True, 0, "SP", "official starter",
    )
    snapshot.appearances[away.key] = away
    snapshot.appearances[home.key] = home
    return snapshot


def refresh_metadata() -> dict:
    return {
        "result": "complete",
        "generated_at": NOW,
        "api_calls": 2,
        "scheduled_games": 1,
        "games_requested": 1,
        "games_fetched": 1,
        "games_failed": 0,
        "current_games": 1,
        "stale_games": 0,
        "missing_games": 0,
    }


def test_check_reloads_and_verifies_written_snapshot(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    result = check_persisted_snapshot(tmp_path, 2026)

    assert result["games"] == 1
    assert result["appearances"] == 2
    assert result["current_games"] == 1


def test_check_rejects_content_changed_after_manifest_was_written(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    appearances = tmp_path / "seasons/2026/appearances/2026-07.jsonl"
    appearances.write_text(appearances.read_text() + "\n")

    with pytest.raises(SnapshotValidationError, match="byte count mismatch"):
        check_persisted_snapshot(tmp_path, 2026)
