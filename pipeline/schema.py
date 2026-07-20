from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GameRecord:
    game_pk: int
    game_date: str
    season: int
    status: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GameRecord":
        return cls(
            game_pk=int(value["game_pk"]),
            game_date=str(value["game_date"]),
            season=int(value["season"]),
            status=str(value["status"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AppearanceRecord:
    game_pk: int
    game_date: str
    season: int
    team_id: int
    team_name: str
    pitcher_id: int
    pitcher_name: str
    pitches: int
    official_started: bool
    appearance_order: int
    adjusted_role: str = "RP"
    classification_reason: str = "unclassified"
    needs_review: bool = False

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.game_pk, self.team_id, self.pitcher_id)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AppearanceRecord":
        return cls(
            game_pk=int(value["game_pk"]),
            game_date=str(value["game_date"]),
            season=int(value["season"]),
            team_id=int(value["team_id"]),
            team_name=str(value["team_name"]),
            pitcher_id=int(value["pitcher_id"]),
            pitcher_name=str(value["pitcher_name"]),
            pitches=int(value["pitches"]),
            official_started=bool(value["official_started"]),
            appearance_order=int(value["appearance_order"]),
            adjusted_role=str(value.get("adjusted_role", "RP")),
            classification_reason=str(value.get("classification_reason", "unclassified")),
            needs_review=bool(value.get("needs_review", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FetchStateRecord:
    game_pk: int
    fetch_status: str
    last_attempt_at: str
    last_success_at: str | None
    last_error: str | None
    attempt_count: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FetchStateRecord":
        return cls(
            game_pk=int(value["game_pk"]),
            fetch_status=str(value["fetch_status"]),
            last_attempt_at=str(value["last_attempt_at"]),
            last_success_at=(str(value["last_success_at"]) if value.get("last_success_at") else None),
            last_error=(str(value["last_error"]) if value.get("last_error") else None),
            attempt_count=int(value["attempt_count"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Snapshot:
    season: int
    games: dict[int, GameRecord] = field(default_factory=dict)
    appearances: dict[tuple[int, int, int], AppearanceRecord] = field(default_factory=dict)
    fetch_state: dict[int, FetchStateRecord] = field(default_factory=dict)
