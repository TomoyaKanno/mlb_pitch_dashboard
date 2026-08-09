from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
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


@dataclass(frozen=True)
class RoleOverridesFile:
    """Parsed config/role_overrides.json: reviewed exceptions plus review marker."""

    overrides: dict[str, Any]
    reviewed_through: str | None


def load_role_overrides(path: Path) -> RoleOverridesFile:
    """Read the overrides config: an ``overrides`` map keyed ``game_pk:pitcher_id``
    and a ``reviewed_through`` date recording the last manual flag review."""
    if not path.exists():
        return RoleOverridesFile({}, None)
    payload = json.loads(path.read_text())
    reviewed = payload.get("reviewed_through")
    return RoleOverridesFile(
        dict(payload.get("overrides", {})),
        str(reviewed) if reviewed is not None else None,
    )


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
    """Classify appearances without treating outing length as role by itself.

    Runs in two passes: official starters first, then relievers, so a reliever
    can see whether his game's starter was classified a relief-dominant opener.
    When it was, the 45+-pitch second pitcher is the planned bulk man and is
    adjusted to SP; a manual override on the opener does not cascade — the
    reviewer sets both halves of an overridden game explicitly.
    """
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

    def surrounding_for(row: Appearance) -> list[Appearance]:
        return [
            other
            for other in by_pitcher[row.pitcher_id]
            if other.game_pk != row.game_pk
            and abs((other.game_date - row.game_date).days) <= window_days
        ]

    result: dict[tuple[int, int, int], Classification] = {}
    for row in rows:
        if not row.official_started:
            continue
        result_key = (row.game_pk, row.team_id, row.pitcher_id)
        override = _override_role(overrides.get(f"{row.game_pk}:{row.pitcher_id}"))
        if override:
            result[result_key] = Classification(override, "manual override")
            continue

        surrounding = surrounding_for(row)
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

    for row in rows:
        if row.official_started:
            continue
        result_key = (row.game_pk, row.team_id, row.pitcher_id)
        override = _override_role(overrides.get(f"{row.game_pk}:{row.pitcher_id}"))
        if override:
            result[result_key] = Classification(override, "manual override")
            continue

        # An opener only classifies relief-dominant when its follower threw 45+,
        # so that follower is the planned bulk man by the same evidence.
        staff = by_game_team[(row.game_pk, row.team_id)]
        opener_result = result.get((row.game_pk, row.team_id, staff[0].pitcher_id))
        if (
            len(staff) >= 2
            and staff[1].pitcher_id == row.pitcher_id
            and opener_result is not None
            and opener_result.reason == "relief-dominant opener"
        ):
            result[result_key] = Classification("SP", "bulk behind relief-dominant opener")
            continue

        surrounding = surrounding_for(row)
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


