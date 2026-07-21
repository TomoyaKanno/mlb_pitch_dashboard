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
      manifest.json
```

Game and appearance records are partitioned by month to keep automated diffs small. Administrative fetch state is separate from baseball facts. The manifest identifies schema version 1, coverage, API calls, failures, and SHA-256 hashes for every data file.

Appearance records include both MLB's official `gamesStarted` designation and the conservative role-adjusted classification. A short, ineffective official start therefore remains an SP unless the established opener rules identify it as relief usage.

## Browser-ready exports

`pipeline.export` projects the validated snapshot into static JSON consumed at Observable build time. These are read models, not a second source of truth:

| Artifact | Loader | Contents |
| --- | --- | --- |
| Season team totals | `observable/src/data/dashboard.json.py` | One row per team plus recent_games: one latest completed game per team with its pitcher pitch counts |
| Team timeseries | `observable/src/data/team-timeseries.json.py` | Daily team increments for the timeline, plus game-grain `complete_games` (0 official RP, with pitcher) |

Daily team points must reconcile to season team totals: summing each metric (and game counts) across dates for a team equals that team's dashboard row. The dashboard derives cumulative series with a prefix sum (`metricSeries`); daily/timecourse mode plots each day's increment (share uses that day's SP/RP split). Role adjustment has no timeline yet.

Recent games are also selected at **game** grain. GameRecord.game_datetime stores MLB's scheduled gameDate, so a doubleheader chooses the later scheduled game even when its game_pk does not sort last. Old snapshots without this optional field use game_pk only until their next normal refresh rewrites the game records.

Complete games are listed at **game** grain, not calendar day: a doubleheader can hide a CG inside a day total that still has RP pitches from the other game. Each `complete_games` row is a `(game_pk, team_id)` with zero official RP pitches and a single pitcher. Player-level series can follow the same sibling-export pattern later; appearance rows are already pitcher-dated.

## Failure behavior

- A failed first fetch is recorded as missing.
- A failed reconciliation fetch preserves the prior appearances and marks them stale.
- Per-game failures do not discard successful games from the same run.
- A schedule that loses a previously completed game is rejected as an unsafe regression.
- Structural errors such as missing teams, missing official starters, duplicate appearance order, or unclassified appearances prevent the snapshot from being written.

The scheduled `Refresh dashboard data` workflow commits only a validated snapshot to the orphan `dashboard-data` branch. A separate least-privilege workflow builds from that revision and gives GitHub Pages an ephemeral artifact.
