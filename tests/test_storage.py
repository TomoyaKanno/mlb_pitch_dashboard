from __future__ import annotations

import pytest

from pipeline.schema import GameRecord, Snapshot
from pipeline.storage import load_snapshot, write_snapshot


def game(game_pk: int, game_date: str) -> GameRecord:
    return GameRecord(
        game_pk,
        game_date,
        2026,
        "Final",
        f"{game_date}T23:10:00Z",
        100,
        "Away",
        200,
        "Home",
    )


def test_write_snapshot_removes_obsolete_month_partitions(tmp_path) -> None:
    first = Snapshot(season=2026)
    first.games = {
        1: game(1, "2026-06-30"),
        2: game(2, "2026-07-01"),
    }
    write_snapshot(first, {}, tmp_path)

    second = Snapshot(season=2026)
    second.games = {2: game(2, "2026-07-01")}
    write_snapshot(second, {}, tmp_path)

    root = tmp_path / "seasons/2026/games"
    assert not (root / "2026-06.jsonl").exists()
    assert (root / "2026-07.jsonl").exists()


def test_load_snapshot_reports_invalid_jsonl_path_and_line(tmp_path) -> None:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = game(1, "2026-07-01")
    write_snapshot(snapshot, {}, tmp_path)
    games_path = tmp_path / "seasons/2026/games/2026-07.jsonl"
    games_path.write_text(games_path.read_text() + "{not-json\n")

    with pytest.raises(ValueError, match=r"2026-07\.jsonl:2"):
        load_snapshot(tmp_path, 2026)


def test_load_snapshot_rejects_duplicate_records_across_partitions(tmp_path) -> None:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = game(1, "2026-07-01")
    write_snapshot(snapshot, {}, tmp_path)
    root = tmp_path / "seasons/2026/games"
    (root / "2026-08.jsonl").write_text((root / "2026-07.jsonl").read_text())

    with pytest.raises(ValueError, match="duplicate game 1"):
        load_snapshot(tmp_path, 2026)
