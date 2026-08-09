from __future__ import annotations

import json
import re
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


_OVERRIDE_KEY = re.compile(r"[0-9]+:[0-9]+")


@dataclass(frozen=True)
class RoleOverridesFile:
    """One season's reviewed exceptions plus its review marker."""

    overrides: dict[str, Any]
    reviewed_through: str | None


def load_role_overrides(path: Path, season: int) -> RoleOverridesFile:
    """Read one season's overrides from the season-keyed config.

    The whole file is validated strictly on every load: this is the audited
    record of manual review decisions, so a malformed entry must fail the
    refresh rather than silently reverting to the heuristic classification.
    """
    if not path.exists():
        return RoleOverridesFile({}, None)
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or set(payload) - {"seasons"}:
        raise ValueError(f"{path}: expected a single top-level 'seasons' object")
    seasons = payload.get("seasons", {})
    if not isinstance(seasons, dict):
        raise ValueError(f"{path}: 'seasons' must be an object keyed by year")
    for season_key, entry in seasons.items():
        context = f"{path}: season {season_key!r}"
        if not re.fullmatch(r"[0-9]{4}", season_key):
            raise ValueError(f"{context} is not a four-digit year")
        if not isinstance(entry, dict) or set(entry) - {"overrides", "reviewed_through"}:
            raise ValueError(f"{context} allows only 'overrides' and 'reviewed_through'")
        reviewed = entry.get("reviewed_through")
        if reviewed is not None:
            try:
                date.fromisoformat(str(reviewed))
            except ValueError as exc:
                raise ValueError(f"{context} has an invalid reviewed_through date") from exc
        overrides = entry.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError(f"{context} overrides must be an object")
        for key, value in overrides.items():
            if not _OVERRIDE_KEY.fullmatch(key):
                raise ValueError(f"{context} override key {key!r} is not 'game_pk:pitcher_id'")
            if not isinstance(value, dict) or set(value) != {"role", "reason"}:
                raise ValueError(f"{context} override {key} must have exactly 'role' and 'reason'")
            if value["role"] not in {"SP", "RP"}:
                raise ValueError(f"{context} override {key} role must be 'SP' or 'RP'")
            if not isinstance(value["reason"], str) or not value["reason"].strip():
                raise ValueError(f"{context} override {key} needs a nonempty reason")
    entry = seasons.get(str(season), {})
    reviewed = entry.get("reviewed_through")
    return RoleOverridesFile(
        dict(entry.get("overrides", {})),
        str(reviewed) if reviewed is not None else None,
    )


def _overridden(overrides: dict[str, Any], row: Appearance) -> Classification | None:
    value = overrides.get(f"{row.game_pk}:{row.pitcher_id}")
    if value is None:
        return None
    role = str(value["role"] if isinstance(value, dict) else value).upper()
    return Classification(role, "manual override")


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
        override = _overridden(overrides, row)
        if override is not None:
            result[result_key] = override
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
        override = _overridden(overrides, row)
        if override is not None:
            result[result_key] = override
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


