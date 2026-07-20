from __future__ import annotations

import json
import sqlite3
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
                """
            )

    def existing_game_pks(self, season: int) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT game_pk FROM games WHERE season = ?", (season,)
            ).fetchall()
        return {int(row["game_pk"]) for row in rows}

    def upsert_game(self, game: dict[str, Any], appearances: list[dict[str, Any]]) -> None:
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

