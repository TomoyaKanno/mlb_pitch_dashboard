# Durable data contract

The build-time pipeline writes normalized, versioned season snapshots. These files are source data for a later static-site build; they are not the built GitHub Pages output.

## Command

```bash
python -m pipeline.update --season 2026 --data-dir ./dashboard-data
```

An empty directory triggers a full bootstrap. Later runs request games that are missing, previously failed, or within the current season's reconciliation window. `--force` requests every completed game, and `--reconcile-days` controls the default seven-day window.

## Layout

```text
dashboard-data/
  seasons/
    2026/
      games/2026-03.jsonl
      appearances/2026-03.jsonl
      fetch-state.json
      next-games.json
      manifest.json
```

Game and appearance records are partitioned by month to keep automated diffs small. Administrative fetch state and the current next-game read model are separate from baseball facts. The manifest identifies schema version 1, coverage, API calls, failures, and SHA-256 hashes for every data file.

Appearance records include both MLB's official `gamesStarted` designation and the conservative role-adjusted classification. A short, ineffective official start therefore remains an SP unless the established opener rules identify it as relief usage.

## Browser-ready exports

`pipeline.export` projects the validated snapshot into static JSON consumed at Observable build time. These are read models, not a second source of truth:

| Artifact | Loader | Contents |
| --- | --- | --- |
| Season dashboard | `observable/src/data/dashboard.json.py` | One season-total row, one latest completed game, one upcoming-game record (with optional probable starter), and one 14-day bullpen-usage window per team |
| Team timeseries | `observable/src/data/team-timeseries.json.py` | Daily team increments for the timeline, plus game-grain `complete_games` (0 official RP, with pitcher) |

Daily team points must reconcile to season team totals: summing each metric (and game counts) across dates for a team equals that team's dashboard row. The dashboard derives cumulative series with a prefix sum (`metricSeries`); daily/timecourse mode plots each day's increment (share uses that day's SP/RP split). Role adjustment has no timeline yet.

Recent games are selected at **game** grain. `GameRecord.game_datetime` stores MLB's scheduled `gameDate`, so a doubleheader chooses the later scheduled game even when its `game_pk` does not sort last. Old snapshots without this optional field use `game_pk` only until their next normal refresh rewrites the game records.

Each `next_games` row is the earliest non-final regular-season game returned for a team in the 14-day schedule window. It includes the opponent and home/away context. MLB may omit a `probable_pitcher`; consumers must display that as unannounced rather than infer one. Existing snapshots created before this read model legitimately export an empty `next_games` list until their next successful refresh.

Each `bullpen_usage` row contains 14 unique, ordered calendar dates ending on that team's latest completed-game date. Pitch arrays align positionally with those dates and contain non-negative official-reliever pitch counts. Doubleheader appearances are summed into the same calendar-day cell; official starters are excluded.

Complete games are listed at **game** grain, not calendar day: a doubleheader can hide a CG inside a day total that still has RP pitches from the other game. Each `complete_games` row is a `(game_pk, team_id)` with zero official RP pitches and a single pitcher. Player-level series can follow the same sibling-export pattern later; appearance rows are already pitcher-dated.

## Failure behavior

- A failed first fetch is recorded as missing.
- A failed reconciliation fetch preserves the prior appearances and marks them stale.
- Per-game failures do not discard successful games from the same run.
- A schedule that loses a previously completed game is rejected as an unsafe regression.
- Structural errors such as missing teams, missing official starters, duplicate appearance order, or unclassified appearances prevent the snapshot from being written.

The scheduled `Refresh dashboard data` workflow commits only a validated snapshot to the orphan `dashboard-data` branch. A separate least-privilege workflow builds from that revision and gives GitHub Pages an ephemeral artifact.
