from app.db import Database


def game(game_pk: int) -> dict:
    return {
        "game_pk": game_pk,
        "game_date": "2026-07-20",
        "season": 2026,
        "status": "Final",
    }


def appearance(game_pk: int) -> dict:
    return {
        "game_pk": game_pk,
        "team_id": 119,
        "team_name": "Los Angeles Dodgers",
        "pitcher_id": 1,
        "pitcher_name": "Test Pitcher",
        "pitches": 88,
        "official_started": True,
        "appearance_order": 0,
    }


def test_failed_refetch_preserves_cache_but_makes_game_retryable(tmp_path):
    database = Database(tmp_path / "mlb.sqlite3")
    item = game(100)
    database.upsert_game(item, [appearance(100)])

    assert database.existing_game_pks(2026) == {100}

    database.record_game_failure(item, "upstream timeout")

    assert database.cached_game_pks(2026) == {100}
    assert database.existing_game_pks(2026) == set()
    assert database.failed_game_pks(2026) == {100}
    assert database.refresh_coverage(2026, [100]) == {
        "scheduled": 1,
        "current": 0,
        "stale": 1,
        "missing": 0,
    }
    failure = database.fetch_failures(2026)[0]
    assert failure["has_cached_data"] == 1
    assert failure["last_error"] == "upstream timeout"


def test_successful_retry_clears_failure_state(tmp_path):
    database = Database(tmp_path / "mlb.sqlite3")
    item = game(101)
    database.record_game_failure(item, "temporary failure")

    assert database.refresh_coverage(2026, [101])["missing"] == 1

    database.upsert_game(item, [appearance(101)])

    assert database.existing_game_pks(2026) == {101}
    assert database.failed_game_pks(2026) == set()
    assert database.fetch_failures(2026) == []
    assert database.refresh_coverage(2026, [101]) == {
        "scheduled": 1,
        "current": 1,
        "stale": 0,
        "missing": 0,
    }


def test_legacy_cached_game_without_fetch_state_is_current(tmp_path):
    database = Database(tmp_path / "mlb.sqlite3")
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(game_pk, game_date, season, status) VALUES (?, ?, ?, ?)",
            (102, "2026-07-20", 2026, "Final"),
        )

    assert database.existing_game_pks(2026) == {102}
