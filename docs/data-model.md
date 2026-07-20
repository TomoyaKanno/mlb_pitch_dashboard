# Data model

SQLite is the durable boundary between MLB API collection and dashboard presentation.

## `games`

One row per MLB game, keyed by `game_pk`. A row exists only after a boxscore was fetched and stored successfully.

## `appearances`

One row per pitcher/team/game appearance. It stores the MLB-reported pitch count and `official_started` flag plus the derived adjusted role, reason, and review flag.

The primary key is `(game_pk, team_id, pitcher_id)`. Re-fetching a game replaces all of its appearances transactionally.

## `game_fetch_state`

One row per game that has been attempted by the current application version:

- `fetch_status`: `success` or `failed`
- `last_attempt_at`: most recent attempt time
- `last_success_at`: most recent successful storage time, if any
- `last_error`: most recent failure message, if any
- `attempt_count`: cumulative completed attempts

A failed game can still have a row in `games`. That means its last-known-good data is retained but stale. A failed game without a `games` row is missing. Both are excluded from `existing_game_pks`, making them eligible for the next incremental refresh.

Older databases may contain games without `game_fetch_state` rows. Those legacy cached games are treated as successful until a later attempt explicitly succeeds or fails.

## `metadata`

Key/value refresh metadata used by `/api/status`, including the latest refresh result and scheduled/current/stale/missing coverage counts.

## Aggregate invariants

For every team and season:

```text
total = official_sp + official_rp
total = adjusted_sp + adjusted_rp
```

Stale cached appearances may remain queryable, but the status endpoint must disclose their count. A future strict-current view can exclude them by joining against `game_fetch_state`.
