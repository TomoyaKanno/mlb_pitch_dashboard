from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .classify import Appearance, classify_appearances, load_role_overrides
from .mlb import MLBClient, fetch_game_batch
from .schema import AppearanceRecord, FetchStateRecord, GameRecord, NextGameRecord, RosterPitcherRecord, Snapshot
from .storage import load_snapshot, write_snapshot
from .validation import SnapshotValidationError, validate_snapshot


@dataclass(frozen=True, slots=True)
class RefreshSummary:
    season: int
    result: str
    generated_at: str
    api_calls: int
    scheduled_games: int
    games_requested: int
    games_fetched: int
    games_failed: int
    current_games: int
    stale_games: int
    missing_games: int
    # Recorded with the snapshot so the marker always describes the
    # classifications actually persisted, not the source checkout's config.
    role_reviewed_through: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def games_to_refresh(
    games: list[GameRecord],
    snapshot: Snapshot,
    *,
    force: bool,
    reconcile_days: int,
    as_of: date,
) -> list[GameRecord]:
    cutoff = as_of - timedelta(days=reconcile_days)
    pending: list[GameRecord] = []
    for game in games:
        state = snapshot.fetch_state.get(game.game_pk)
        has_data = any(key[0] == game.game_pk for key in snapshot.appearances)
        recent = game.season == as_of.year and date.fromisoformat(game.game_date) >= cutoff
        if force or state is None or state.fetch_status == "failed" or not has_data or recent:
            pending.append(game)
    return pending


def _classify(snapshot: Snapshot, overrides: dict[str, Any]) -> None:
    inputs = [
        Appearance(
            game_pk=row.game_pk,
            game_date=date.fromisoformat(row.game_date),
            team_id=row.team_id,
            pitcher_id=row.pitcher_id,
            pitches=row.pitches,
            official_started=row.official_started,
            appearance_order=row.appearance_order,
        )
        for row in snapshot.appearances.values()
    ]
    classifications = classify_appearances(inputs, overrides)
    snapshot.appearances = {
        key: replace(
            row,
            adjusted_role=classifications[key].role,
            classification_reason=classifications[key].reason,
            needs_review=classifications[key].needs_review,
        )
        for key, row in snapshot.appearances.items()
    }


async def update_season(
    season: int,
    data_dir: Path,
    *,
    force: bool = False,
    reconcile_days: int = 7,
    overrides: dict[str, Any] | None = None,
    role_reviewed_through: str | None = None,
    now: datetime | None = None,
    client_factory: Callable[[], Any] = MLBClient,
) -> RefreshSummary:
    if reconcile_days < 0:
        raise ValueError("reconcile_days must be zero or greater")
    now = now or datetime.now(timezone.utc)
    attempted_at = now.astimezone(timezone.utc).isoformat()
    snapshot = load_snapshot(data_dir, season)

    async with client_factory() as client:
        schedule_values = await client.completed_games(season)
        upcoming_values = await client.upcoming_games(season)
        roster_values = await client.pitching_rosters(season)
        scheduled = [GameRecord.from_dict(value) for value in schedule_values]
        next_games = [NextGameRecord.from_dict(value) for value in upcoming_values]
        next_games_by_team = {row.team_id: row for row in next_games}
        if len(next_games_by_team) != len(next_games):
            raise SnapshotValidationError("upcoming schedule contains duplicate teams")
        roster_pitchers = [RosterPitcherRecord.from_dict(value) for value in roster_values]
        roster_by_key = {row.key: row for row in roster_pitchers}
        if len(roster_by_key) != len(roster_pitchers):
            raise SnapshotValidationError("pitching roster contains duplicate team/pitcher rows")
        scheduled_by_pk = {game.game_pk: game for game in scheduled}
        if len(scheduled_by_pk) != len(scheduled):
            raise SnapshotValidationError("schedule contains duplicate game identifiers")
        disappeared = set(snapshot.games) - set(scheduled_by_pk)
        if disappeared:
            raise SnapshotValidationError(
                f"schedule lost {len(disappeared)} previously completed games; refusing to overwrite snapshot"
            )

        snapshot.games = scheduled_by_pk
        snapshot.next_games = next_games_by_team
        snapshot.roster_pitchers = roster_by_key
        pending = games_to_refresh(
            scheduled,
            snapshot,
            force=force,
            reconcile_days=reconcile_days,
            as_of=now.date(),
        )

        async def save(game_value: dict[str, Any], values: list[dict[str, Any]]) -> None:
            game = scheduled_by_pk[int(game_value["game_pk"])]
            snapshot.appearances = {
                key: row for key, row in snapshot.appearances.items() if row.game_pk != game.game_pk
            }
            for value in values:
                row = AppearanceRecord(
                    game_pk=game.game_pk,
                    game_date=game.game_date,
                    season=game.season,
                    team_id=int(value["team_id"]),
                    team_name=str(value["team_name"]),
                    pitcher_id=int(value["pitcher_id"]),
                    pitcher_name=str(value["pitcher_name"]),
                    pitches=int(value["pitches"]),
                    official_started=bool(value["official_started"]),
                    appearance_order=int(value["appearance_order"]),
                )
                if row.key in snapshot.appearances:
                    raise SnapshotValidationError(f"duplicate appearance returned by MLB: {row.key}")
                snapshot.appearances[row.key] = row
            previous = snapshot.fetch_state.get(game.game_pk)
            snapshot.fetch_state[game.game_pk] = FetchStateRecord(
                game_pk=game.game_pk,
                fetch_status="success",
                last_attempt_at=attempted_at,
                last_success_at=attempted_at,
                last_error=None,
                attempt_count=(previous.attempt_count if previous else 0) + 1,
            )

        pending_values = [game.to_dict() for game in pending]
        failures = await fetch_game_batch(client, pending_values, save)
        for game_value, error in failures:
            game_pk = int(game_value["game_pk"])
            previous = snapshot.fetch_state.get(game_pk)
            snapshot.fetch_state[game_pk] = FetchStateRecord(
                game_pk=game_pk,
                fetch_status="failed",
                last_attempt_at=attempted_at,
                last_success_at=previous.last_success_at if previous else None,
                last_error=error,
                attempt_count=(previous.attempt_count if previous else 0) + 1,
            )

        api_calls = int(client.api_calls)

    _classify(snapshot, overrides or {})
    # Overrides are the audited record of manual review; a key that matches no
    # persisted appearance is a typo or a wrong-season entry, never a no-op.
    unmatched = set(overrides or {}) - {
        f"{game_pk}:{pitcher_id}" for game_pk, _team_id, pitcher_id in snapshot.appearances
    }
    if unmatched:
        raise SnapshotValidationError(
            "role overrides reference no persisted appearance: " + ", ".join(sorted(unmatched))
        )
    validate_snapshot(snapshot)

    scheduled_pks = set(scheduled_by_pk)
    data_pks = {row.game_pk for row in snapshot.appearances.values()}
    current = {
        game_pk
        for game_pk, state in snapshot.fetch_state.items()
        if game_pk in scheduled_pks and state.fetch_status == "success" and game_pk in data_pks
    }
    stale = {
        game_pk
        for game_pk, state in snapshot.fetch_state.items()
        if game_pk in scheduled_pks and state.fetch_status == "failed" and game_pk in data_pks
    }
    missing = scheduled_pks - current - stale
    result = "complete" if not failures else ("failed" if len(failures) == len(pending) and not current else "partial")
    summary = RefreshSummary(
        season=season,
        result=result,
        generated_at=attempted_at,
        api_calls=api_calls,
        scheduled_games=len(scheduled),
        games_requested=len(pending),
        games_fetched=len(pending) - len(failures),
        games_failed=len(failures),
        current_games=len(current),
        stale_games=len(stale),
        missing_games=len(missing),
        role_reviewed_through=role_reviewed_through,
    )
    write_snapshot(snapshot, summary.to_dict(), data_dir)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update a durable MLB season snapshot")
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reconcile-days", type=int, default=7)
    parser.add_argument("--overrides", type=Path, default=Path("config/role_overrides.json"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    overrides_file = load_role_overrides(args.overrides, args.season)
    summary = asyncio.run(
        update_season(
            args.season,
            args.data_dir,
            force=args.force,
            reconcile_days=args.reconcile_days,
            overrides=overrides_file.overrides,
            role_reviewed_through=overrides_file.reviewed_through,
        )
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
