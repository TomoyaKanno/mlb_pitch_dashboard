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
    game_datetime: str
    away_team_id: int
    away_team_name: str
    home_team_id: int
    home_team_name: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GameRecord":
        return cls(
            game_pk=int(value["game_pk"]),
            game_date=str(value["game_date"]),
            season=int(value["season"]),
            status=str(value["status"]),
            game_datetime=str(value["game_datetime"]),
            away_team_id=int(value["away_team_id"]),
            away_team_name=str(value["away_team_name"]),
            home_team_id=int(value["home_team_id"]),
            home_team_name=str(value["home_team_name"]),
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
            adjusted_role=str(value["adjusted_role"]),
            classification_reason=str(value["classification_reason"]),
            needs_review=bool(value["needs_review"]),
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


@dataclass(frozen=True, slots=True)
class NextGameRecord:
    team_id: int
    team_name: str
    game_pk: int
    game_date: str
    game_datetime: str
    opponent_id: int
    opponent_name: str
    is_home: bool
    probable_pitcher_id: int | None
    probable_pitcher_name: str | None
    is_rest_day_today: bool
    schedule_date: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NextGameRecord":
        return cls(
            team_id=int(value["team_id"]),
            team_name=str(value["team_name"]),
            game_pk=int(value["game_pk"]),
            game_date=str(value["game_date"]),
            game_datetime=str(value["game_datetime"]),
            opponent_id=int(value["opponent_id"]),
            opponent_name=str(value["opponent_name"]),
            is_home=bool(value["is_home"]),
            probable_pitcher_id=(
                int(value["probable_pitcher_id"])
                if value.get("probable_pitcher_id") is not None
                else None
            ),
            probable_pitcher_name=(
                str(value["probable_pitcher_name"])
                if value.get("probable_pitcher_name")
                else None
            ),
            is_rest_day_today=bool(value["is_rest_day_today"]),
            schedule_date=str(value["schedule_date"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RosterPitcherRecord:
    """Published pitching depth / 40-man status for Recent strain context.

    ``depth_role`` is set for arms listed on MLB's depth chart (``SP``, ``RP``
    for bullpen ``P``, or ``CP``). Pitchers present only on the 40-man roster
    keep a null depth role. Status codes come from MLB (``A``, ``D15``, ``RM``, …).
    """

    team_id: int
    team_name: str
    pitcher_id: int
    pitcher_name: str
    depth_role: str | None
    depth_order: int | None
    status_code: str
    status_description: str

    @property
    def key(self) -> tuple[int, int]:
        return (self.team_id, self.pitcher_id)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RosterPitcherRecord":
        return cls(
            team_id=int(value["team_id"]),
            team_name=str(value["team_name"]),
            pitcher_id=int(value["pitcher_id"]),
            pitcher_name=str(value["pitcher_name"]),
            depth_role=(str(value["depth_role"]) if value.get("depth_role") else None),
            depth_order=(
                int(value["depth_order"]) if value.get("depth_order") is not None else None
            ),
            status_code=str(value["status_code"]),
            status_description=str(value["status_description"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Snapshot:
    season: int
    games: dict[int, GameRecord] = field(default_factory=dict)
    appearances: dict[tuple[int, int, int], AppearanceRecord] = field(default_factory=dict)
    fetch_state: dict[int, FetchStateRecord] = field(default_factory=dict)
    next_games: dict[int, NextGameRecord] = field(default_factory=dict)
    roster_pitchers: dict[tuple[int, int], RosterPitcherRecord] = field(default_factory=dict)
