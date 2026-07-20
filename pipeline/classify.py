from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class Appearance:
    game_pk: int
    game_date: date
    team_id: int
    pitcher_id: int
    pitches: int
    official_started: bool
    appearance_order: int


@dataclass(frozen=True)
class Classification:
    role: str
    reason: str
    needs_review: bool = False


def _override_role(value: Any) -> str | None:
    if isinstance(value, str):
        role = value.upper()
    elif isinstance(value, dict):
        role = str(value.get("role", "")).upper()
    else:
        return None
    return role if role in {"SP", "RP"} else None


def classify_appearances(
    appearances: Iterable[Appearance],
    overrides: dict[str, Any] | None = None,
    window_days: int = 28,
) -> dict[tuple[int, int, int], Classification]:
    """Classify appearances without treating outing length as role by itself."""
    rows = list(appearances)
    overrides = overrides or {}
    by_pitcher: dict[int, list[Appearance]] = defaultdict(list)
    by_game_team: dict[tuple[int, int], list[Appearance]] = defaultdict(list)

    for row in rows:
        by_pitcher[row.pitcher_id].append(row)
        by_game_team[(row.game_pk, row.team_id)].append(row)

    for pitcher_rows in by_pitcher.values():
        pitcher_rows.sort(key=lambda item: (item.game_date, item.game_pk))
    for game_rows in by_game_team.values():
        game_rows.sort(key=lambda item: item.appearance_order)

    result: dict[tuple[int, int, int], Classification] = {}
    for row in rows:
        result_key = (row.game_pk, row.team_id, row.pitcher_id)
        override = _override_role(overrides.get(f"{row.game_pk}:{row.pitcher_id}"))
        if override:
            result[result_key] = Classification(override, "manual override")
            continue

        surrounding = [
            other
            for other in by_pitcher[row.pitcher_id]
            if other.game_pk != row.game_pk
            and abs((other.game_date - row.game_date).days) <= window_days
        ]

        if row.official_started:
            starts = sum(item.official_started for item in surrounding)
            relief_rows = [item for item in surrounding if not item.official_started]
            start_share = starts / len(surrounding) if surrounding else 1.0
            relief_median = median(item.pitches for item in relief_rows) if relief_rows else 999
            staff = by_game_team[(row.game_pk, row.team_id)]
            current_index = staff.index(row)
            follower = staff[current_index + 1] if current_index + 1 < len(staff) else None
            relief_dominant = len(surrounding) >= 3 and start_share < 0.25 and relief_median <= 35
            opener_shape = row.pitches <= 40 and follower is not None and follower.pitches >= 45

            if relief_dominant and opener_shape:
                result[result_key] = Classification("RP", "relief-dominant opener")
            else:
                result[result_key] = Classification("SP", "official starter")
            continue

        has_nearby_start = any(item.official_started for item in surrounding)
        if row.pitches >= 45 and has_nearby_start:
            result[result_key] = Classification("SP", "starter-identity bulk appearance")
        elif row.pitches >= 55:
            result[result_key] = Classification(
                "RP",
                "long relief outing without MLB starter evidence",
                needs_review=True,
            )
        else:
            result[result_key] = Classification("RP", "official reliever")

    return result


