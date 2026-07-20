from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .classify import Appearance, Classification


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_pk INTEGER PRIMARY KEY,
                    game_date TEXT NOT NULL,
                    season INTEGER NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS appearances (
                    game_pk INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    pitcher_id INTEGER NOT NULL,
                    pitcher_name TEXT NOT NULL,
                    pitches INTEGER NOT NULL,
                    official_started INTEGER NOT NULL,
                    appearance_order INTEGER NOT NULL,
                    adjusted_role TEXT NOT NULL DEFAULT 'RP',
                    classification_reason TEXT NOT NULL DEFAULT 'unclassified',
                    needs_review INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (game_pk, team_id, pitcher_id),
                    FOREIGN KEY (game_pk) REFERENCES games(game_pk) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_appearances_pitcher
                    ON appearances(pitcher_id, game_pk);
                CREATE INDEX IF NOT EXISTS idx_appearances_team
                    ON appearances(team_id, game_pk);

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS game_fetch_state (
                    game_pk INTEGER PRIMARY KEY,
                    season INTEGER NOT NULL,
                    game_date TEXT NOT NULL,
                    fetch_status TEXT NOT NULL CHECK(fetch_status IN ('success', 'failed')),
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    last_error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_game_fetch_state_season_status
                    ON game_fetch_state(season, fetch_status);
                """
            )

    def existing_game_pks(self, season: int) -> set[int]:
        """Return cached games that are eligible to be treated as current.

        Legacy rows without a fetch-state record are considered successful.
        Once a later fetch fails, the failure record makes that game retryable
        even though its last-known-good appearances remain available.
        """
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.game_pk
                FROM games g
                LEFT JOIN game_fetch_state f USING(game_pk)
                WHERE g.season = ?
                  AND COALESCE(f.fetch_status, 'success') = 'success'
                """,
                (season,),
            ).fetchall()
        return {int(row["game_pk"]) for row in rows}

    def cached_game_pks(self, season: int) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT game_pk FROM games WHERE season = ?", (season,)
            ).fetchall()
        return {int(row["game_pk"]) for row in rows}

    def failed_game_pks(self, season: int) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT game_pk
                FROM game_fetch_state
                WHERE season = ? AND fetch_status = 'failed'
                """,
                (season,),
            ).fetchall()
        return {int(row["game_pk"]) for row in rows}

    def upsert_game(self, game: dict[str, Any], appearances: list[dict[str, Any]]) -> None:
        attempted_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO games(game_pk, game_date, season, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(game_pk) DO UPDATE SET
                    game_date = excluded.game_date,
                    season = excluded.season,
                    status = excluded.status
                """,
                (game["game_pk"], game["game_date"], game["season"], game["status"]),
            )
            connection.execute("DELETE FROM appearances WHERE game_pk = ?", (game["game_pk"],))
            connection.executemany(
                """
                INSERT INTO appearances(
                    game_pk, team_id, team_name, pitcher_id, pitcher_name,
                    pitches, official_started, appearance_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["game_pk"],
                        item["team_id"],
                        item["team_name"],
                        item["pitcher_id"],
                        item["pitcher_name"],
                        item["pitches"],
                        int(item["official_started"]),
                        item["appearance_order"],
                    )
                    for item in appearances
                ],
            )
            connection.execute(
                """
                INSERT INTO game_fetch_state(
                    game_pk, season, game_date, fetch_status,
                    last_attempt_at, last_success_at, last_error, attempt_count
                ) VALUES (?, ?, ?, 'success', ?, ?, NULL, 1)
                ON CONFLICT(game_pk) DO UPDATE SET
                    season = excluded.season,
                    game_date = excluded.game_date,
                    fetch_status = 'success',
                    last_attempt_at = excluded.last_attempt_at,
                    last_success_at = excluded.last_success_at,
                    last_error = NULL,
                    attempt_count = game_fetch_state.attempt_count + 1
                """,
                (
                    game["game_pk"],
                    game["season"],
                    game["game_date"],
                    attempted_at,
                    attempted_at,
                ),
            )

    def record_game_failure(self, game: dict[str, Any], error: str) -> None:
        """Mark a game retryable without deleting its last-known-good data."""
        attempted_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO game_fetch_state(
                    game_pk, season, game_date, fetch_status,
                    last_attempt_at, last_success_at, last_error, attempt_count
                ) VALUES (?, ?, ?, 'failed', ?, NULL, ?, 1)
                ON CONFLICT(game_pk) DO UPDATE SET
                    season = excluded.season,
                    game_date = excluded.game_date,
                    fetch_status = 'failed',
                    last_attempt_at = excluded.last_attempt_at,
                    last_error = excluded.last_error,
                    attempt_count = game_fetch_state.attempt_count + 1
                """,
                (
                    game["game_pk"],
                    game["season"],
                    game["game_date"],
                    attempted_at,
                    error,
                ),
            )

    def refresh_coverage(self, season: int, scheduled_game_pks: Iterable[int]) -> dict[str, int]:
        """Summarize current, stale, and missing games for one schedule snapshot."""
        scheduled = {int(game_pk) for game_pk in scheduled_game_pks}
        cached = self.cached_game_pks(season) & scheduled
        current = self.existing_game_pks(season) & scheduled
        failed = self.failed_game_pks(season) & scheduled
        stale = cached & failed
        missing = scheduled - current - stale
        return {
            "scheduled": len(scheduled),
            "current": len(current),
            "stale": len(stale),
            "missing": len(missing),
        }

    def fetch_failures(self, season: int, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT game_pk, season, game_date, last_attempt_at,
                       last_success_at, last_error, attempt_count,
                       CASE WHEN EXISTS(
                           SELECT 1 FROM games g WHERE g.game_pk = game_fetch_state.game_pk
                       ) THEN 1 ELSE 0 END AS has_cached_data
                FROM game_fetch_state
                WHERE season = ? AND fetch_status = 'failed'
                ORDER BY game_date DESC, game_pk DESC
                LIMIT ?
                """,
                (season, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def all_appearances(self, season: int) -> list[Appearance]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.game_pk, g.game_date, a.team_id, a.pitcher_id,
                       a.pitches, a.official_started, a.appearance_order
                FROM appearances a
                JOIN games g USING(game_pk)
                WHERE g.season = ?
                ORDER BY g.game_date, a.game_pk, a.team_id, a.appearance_order
                """,
                (season,),
            ).fetchall()
        from datetime import date

        return [
            Appearance(
                game_pk=int(row["game_pk"]),
                game_date=date.fromisoformat(row["game_date"]),
                team_id=int(row["team_id"]),
                pitcher_id=int(row["pitcher_id"]),
                pitches=int(row["pitches"]),
                official_started=bool(row["official_started"]),
                appearance_order=int(row["appearance_order"]),
            )
            for row in rows
        ]

    def save_classifications(
        self,
        classifications: dict[tuple[int, int, int], Classification],
    ) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                UPDATE appearances
                SET adjusted_role = ?, classification_reason = ?, needs_review = ?
                WHERE game_pk = ? AND team_id = ? AND pitcher_id = ?
                """,
                [
                    (
                        value.role,
                        value.reason,
                        int(value.needs_review),
                        key[0],
                        key[1],
                        key[2],
                    )
                    for key, value in classifications.items()
                ],
            )

    def team_totals(self, season: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    a.team_id,
                    a.team_name,
                    COUNT(DISTINCT a.game_pk) AS games,
                    SUM(a.pitches) AS total,
                    SUM(CASE WHEN a.official_started = 1 THEN a.pitches ELSE 0 END) AS official_sp,
                    SUM(CASE WHEN a.official_started = 0 THEN a.pitches ELSE 0 END) AS official_rp,
                    SUM(CASE WHEN a.adjusted_role = 'SP' THEN a.pitches ELSE 0 END) AS adjusted_sp,
                    SUM(CASE WHEN a.adjusted_role = 'RP' THEN a.pitches ELSE 0 END) AS adjusted_rp,
                    SUM(CASE WHEN a.official_started = 0 AND a.adjusted_role = 'SP' THEN a.pitches ELSE 0 END) AS bulk_to_sp,
                    SUM(CASE WHEN a.official_started = 1 AND a.adjusted_role = 'RP' THEN a.pitches ELSE 0 END) AS opener_to_rp,
                    SUM(a.needs_review) AS review_count
                FROM appearances a
                JOIN games g USING(game_pk)
                WHERE g.season = ?
                GROUP BY a.team_id, a.team_name
                ORDER BY total DESC
                """,
                (season,),
            ).fetchall()
        return [dict(row) for row in rows]

    def audit(self, season: int, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.game_date, a.*
                FROM appearances a
                JOIN games g USING(game_pk)
                WHERE g.season = ?
                  AND (a.needs_review = 1 OR
                       (a.official_started = 1 AND a.adjusted_role = 'RP') OR
                       (a.official_started = 0 AND a.adjusted_role = 'SP'))
                ORDER BY g.game_date DESC, a.game_pk DESC, a.appearance_order
                LIMIT ?
                """,
                (season, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_metadata(self, values: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [(key, json.dumps(value)) for key, value in values.items()],
            )

    def metadata(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT key, value FROM metadata").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}
