from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from pipeline.check import check_persisted_snapshot
from pipeline.schema import AppearanceRecord, FetchStateRecord, GameRecord, Snapshot
from pipeline.storage import write_snapshot
from pipeline.validation import SnapshotValidationError


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc).isoformat()


def valid_snapshot() -> Snapshot:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = GameRecord(
        1, "2026-07-19", 2026, "Final", "2026-07-19T23:10:00Z",
        100, "Away", 200, "Home",
    )
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


def test_check_requires_manifest(tmp_path):
    with pytest.raises(SnapshotValidationError, match="missing manifest"):
        check_persisted_snapshot(tmp_path, 2026)


def test_check_rejects_content_changed_after_manifest_was_written(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    appearances = tmp_path / "seasons/2026/appearances/2026-07.jsonl"
    appearances.write_text(appearances.read_text() + "\n")

    with pytest.raises(SnapshotValidationError, match="byte count mismatch"):
        check_persisted_snapshot(tmp_path, 2026)


def test_check_rejects_same_length_content_tampering(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    appearances = tmp_path / "seasons/2026/appearances/2026-07.jsonl"
    appearances.write_text(appearances.read_text().replace("Away Starter", "Home Starter"))

    with pytest.raises(SnapshotValidationError, match="SHA-256 mismatch"):
        check_persisted_snapshot(tmp_path, 2026)


@pytest.mark.parametrize(
    "filename",
    ["fetch-state.json", "next-games.json", "roster-pitchers.json"],
)
def test_check_reports_missing_administrative_file_as_contract_failure(
    tmp_path,
    filename: str,
):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    (tmp_path / "seasons/2026" / filename).unlink()

    with pytest.raises(SnapshotValidationError, match="manifest file set mismatch"):
        check_persisted_snapshot(tmp_path, 2026)


def test_check_rejects_unexpected_partition(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    unexpected = tmp_path / "seasons/2026/games/2026-01.jsonl"
    unexpected.write_text("")

    with pytest.raises(SnapshotValidationError, match="manifest file set mismatch"):
        check_persisted_snapshot(tmp_path, 2026)


def test_check_rejects_invalid_manifest_json(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    manifest_path = tmp_path / "seasons/2026/manifest.json"
    manifest_path.write_text("{not-json")

    with pytest.raises(SnapshotValidationError, match="invalid manifest"):
        check_persisted_snapshot(tmp_path, 2026)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 999, "unsupported schema version"),
        ("season", 2025, "another season"),
        ("files", [], "manifest files must be an object"),
    ],
)
def test_check_rejects_invalid_manifest_contract(tmp_path, field, value, message):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    manifest_path = tmp_path / "seasons/2026/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(SnapshotValidationError, match=message):
        check_persisted_snapshot(tmp_path, 2026)


def test_check_rejects_manifest_coverage_drift(tmp_path):
    write_snapshot(valid_snapshot(), refresh_metadata(), tmp_path)
    manifest_path = tmp_path / "seasons/2026/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["current_games"] = 0
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(SnapshotValidationError, match="manifest current_games"):
        check_persisted_snapshot(tmp_path, 2026)
