from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

import pytest

from pipeline.schema import (
    AppearanceRecord,
    FetchStateRecord,
    GameRecord,
    NextGameRecord,
    RosterPitcherRecord,
    Snapshot,
)
from pipeline.validation import SnapshotValidationError, validate_snapshot


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc).isoformat()
Mutation = Callable[[Snapshot], None]


def valid_snapshot() -> Snapshot:
    snapshot = Snapshot(season=2026)
    snapshot.games[1] = GameRecord(
        1,
        "2026-07-19",
        2026,
        "Final",
        "2026-07-19T23:10:00Z",
        100,
        "Away",
        200,
        "Home",
    )
    snapshot.fetch_state[1] = FetchStateRecord(1, "success", NOW, NOW, None, 1)
    away = AppearanceRecord(
        1,
        "2026-07-19",
        2026,
        100,
        "Away",
        11,
        "Away Starter",
        88,
        True,
        0,
        "SP",
        "official starter",
    )
    home = AppearanceRecord(
        1,
        "2026-07-19",
        2026,
        200,
        "Home",
        21,
        "Home Starter",
        91,
        True,
        0,
        "SP",
        "official starter",
    )
    snapshot.appearances[away.key] = away
    snapshot.appearances[home.key] = home
    snapshot.next_games[100] = NextGameRecord(
        100,
        "Away",
        2,
        "2026-07-21",
        "2026-07-21T23:10:00Z",
        200,
        "Home",
        False,
        None,
        None,
        False,
        "2026-07-20",
    )
    roster = RosterPitcherRecord(
        100,
        "Away",
        11,
        "Away Starter",
        "SP",
        0,
        "A",
        "Active",
    )
    snapshot.roster_pitchers[roster.key] = roster
    return snapshot


def _replace(mapping: dict, key, **changes) -> None:
    mapping[key] = replace(mapping[key], **changes)


def _move(mapping: dict, old_key, new_key) -> None:
    mapping[new_key] = mapping.pop(old_key)


def _appearance_references_missing_game(snapshot: Snapshot) -> None:
    row = replace(snapshot.appearances.pop((1, 100, 11)), game_pk=2)
    snapshot.appearances[row.key] = row


def _fetch_state_references_missing_game(snapshot: Snapshot) -> None:
    row = replace(snapshot.fetch_state.pop(1), game_pk=2)
    snapshot.fetch_state[2] = row


def _duplicate_appearance_order(snapshot: Snapshot) -> None:
    row = AppearanceRecord(
        1,
        "2026-07-19",
        2026,
        100,
        "Away",
        12,
        "Away Reliever",
        20,
        False,
        0,
        "RP",
        "official reliever",
    )
    snapshot.appearances[row.key] = row


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(
            lambda snapshot: _move(snapshot.next_games, 100, 101),
            "next-game dictionary key mismatch",
            id="next-game-key",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.next_games, 100, opponent_id=100),
            "same team and opponent",
            id="next-game-self-opponent",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.next_games, 100, team_name=""),
            "missing a team name",
            id="next-game-name",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.next_games, 100, schedule_date="July 20"),
            "invalid schedule date",
            id="next-game-date",
        ),
        pytest.param(
            lambda snapshot: _replace(
                snapshot.next_games,
                100,
                is_rest_day_today=True,
                game_date="2026-07-20",
            ),
            "marks a rest day without a later next game",
            id="next-game-rest-day",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.next_games, 100, probable_pitcher_id=11),
            "incomplete probable-pitcher data",
            id="next-game-probable",
        ),
        pytest.param(
            lambda snapshot: _move(snapshot.roster_pitchers, (100, 11), (100, 12)),
            "roster pitcher dictionary key mismatch",
            id="roster-key",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.roster_pitchers, (100, 11), pitcher_name=""),
            "missing a name",
            id="roster-name",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.roster_pitchers, (100, 11), status_code=""),
            "missing status",
            id="roster-status",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.roster_pitchers, (100, 11), depth_role="UTIL"),
            "invalid depth role",
            id="roster-role",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.roster_pitchers, (100, 11), depth_order=None),
            "incomplete depth fields",
            id="roster-depth-fields",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.roster_pitchers, (100, 11), depth_order=-1),
            "invalid depth order",
            id="roster-depth-order",
        ),
        pytest.param(
            lambda snapshot: _move(snapshot.games, 1, 2),
            "game dictionary key mismatch",
            id="game-key",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.games, 1, season=2025),
            "belongs to season 2025",
            id="game-season",
        ),
        pytest.param(
            lambda snapshot: snapshot.fetch_state.pop(1),
            "has no fetch state",
            id="game-fetch-state",
        ),
        pytest.param(
            lambda snapshot: _move(snapshot.appearances, (1, 100, 11), (1, 100, 12)),
            "appearance dictionary key mismatch",
            id="appearance-key",
        ),
        pytest.param(
            _appearance_references_missing_game,
            "references missing game",
            id="appearance-game",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.appearances, (1, 100, 11), season=2025),
            "disagrees with its game",
            id="appearance-season",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.appearances, (1, 100, 11), game_date="2026-07-18"),
            "disagrees with its game",
            id="appearance-date",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.appearances, (1, 100, 11), pitches=0),
            "non-positive pitches",
            id="appearance-pitches",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.appearances, (1, 100, 11), adjusted_role="BULK"),
            "invalid adjusted role",
            id="appearance-role",
        ),
        pytest.param(
            lambda snapshot: _replace(
                snapshot.appearances,
                (1, 100, 11),
                classification_reason="unclassified",
            ),
            "has not been classified",
            id="appearance-classification",
        ),
        pytest.param(
            _fetch_state_references_missing_game,
            "fetch state 2 references missing game",
            id="fetch-state-game",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.fetch_state, 1, fetch_status="pending"),
            "invalid fetch status",
            id="fetch-state-status",
        ),
        pytest.param(
            lambda snapshot: _replace(snapshot.fetch_state, 1, attempt_count=0),
            "invalid attempt count",
            id="fetch-state-attempts",
        ),
        pytest.param(
            lambda snapshot: snapshot.appearances.clear(),
            "successful game 1 has no appearances",
            id="fetch-state-success-data",
        ),
        pytest.param(
            _duplicate_appearance_order,
            "duplicate appearance order",
            id="game-team-order",
        ),
        pytest.param(
            lambda snapshot: _replace(
                snapshot.appearances,
                (1, 100, 11),
                official_started=False,
                adjusted_role="RP",
                classification_reason="official reliever",
            ),
            "has 0 official starters",
            id="game-team-starter",
        ),
    ],
)
def test_snapshot_validation_rejects_contract_violations(
    mutate: Mutation,
    message: str,
) -> None:
    snapshot = valid_snapshot()
    mutate(snapshot)

    with pytest.raises(SnapshotValidationError, match=message):
        validate_snapshot(snapshot)


def test_snapshot_validation_accepts_the_complete_contract() -> None:
    validate_snapshot(valid_snapshot())
