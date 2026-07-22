from __future__ import annotations

from collections import defaultdict

from .schema import Snapshot


class SnapshotValidationError(ValueError):
    """Raised when a snapshot would make published totals untrustworthy."""


def validate_snapshot(snapshot: Snapshot) -> None:
    errors: list[str] = []
    by_game_team: dict[tuple[int, int], list] = defaultdict(list)
    appearances_by_game: dict[int, int] = defaultdict(int)

    for team_id, next_game in snapshot.next_games.items():
        if team_id != next_game.team_id:
            errors.append(f"next-game dictionary key mismatch for {team_id}")
        if next_game.team_id == next_game.opponent_id:
            errors.append(f"next game {next_game.game_pk} has the same team and opponent")
        if not next_game.team_name or not next_game.opponent_name:
            errors.append(f"next game {next_game.game_pk} is missing a team name")
        if bool(next_game.probable_pitcher_id is None) != bool(next_game.probable_pitcher_name is None):
            errors.append(f"next game {next_game.game_pk} has incomplete probable-pitcher data")

    for game_pk, game in snapshot.games.items():
        if game_pk != game.game_pk:
            errors.append(f"game dictionary key mismatch for {game_pk}")
        if game.season != snapshot.season:
            errors.append(f"game {game_pk} belongs to season {game.season}")
        if game_pk not in snapshot.fetch_state:
            errors.append(f"game {game_pk} has no fetch state")

    for key, row in snapshot.appearances.items():
        if key != row.key:
            errors.append(f"appearance dictionary key mismatch for {key}")
        game = snapshot.games.get(row.game_pk)
        if game is None:
            errors.append(f"appearance {key} references missing game")
            continue
        if row.season != snapshot.season or row.game_date != game.game_date:
            errors.append(f"appearance {key} disagrees with its game")
        if row.pitches <= 0:
            errors.append(f"appearance {key} has non-positive pitches")
        if row.adjusted_role not in {"SP", "RP"}:
            errors.append(f"appearance {key} has invalid adjusted role")
        if row.classification_reason == "unclassified":
            errors.append(f"appearance {key} has not been classified")
        appearances_by_game[row.game_pk] += 1
        by_game_team[(row.game_pk, row.team_id)].append(row)

    for game_pk, state in snapshot.fetch_state.items():
        if game_pk not in snapshot.games:
            errors.append(f"fetch state {game_pk} references missing game")
        if state.fetch_status not in {"success", "failed"}:
            errors.append(f"game {game_pk} has invalid fetch status")
        if state.attempt_count < 1:
            errors.append(f"game {game_pk} has invalid attempt count")
        if state.fetch_status == "success" and appearances_by_game[game_pk] == 0:
            errors.append(f"successful game {game_pk} has no appearances")

    for game_pk, state in snapshot.fetch_state.items():
        if state.fetch_status != "success":
            continue
        teams = [key for key in by_game_team if key[0] == game_pk]
        if len(teams) != 2:
            errors.append(f"successful game {game_pk} has {len(teams)} pitching teams")
        for game_team in teams:
            rows = by_game_team[game_team]
            orders = [row.appearance_order for row in rows]
            if len(orders) != len(set(orders)):
                errors.append(f"game/team {game_team} has duplicate appearance order")
            starters = sum(row.official_started for row in rows)
            if starters != 1:
                errors.append(f"game/team {game_team} has {starters} official starters")

    if errors:
        preview = "; ".join(errors[:10])
        remainder = len(errors) - 10
        if remainder:
            preview += f"; and {remainder} more"
        raise SnapshotValidationError(preview)
