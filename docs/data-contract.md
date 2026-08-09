# Durable data contract

The refresh pipeline writes normalized season snapshots for a later static-site build. They are source data, not compiled Pages output.

```bash
python -m pipeline.update --season 2026 --data-dir ./dashboard-data
```

An empty directory bootstraps the season. Later runs fetch missing games, prior failures, and games inside the reconciliation window; `--force` intentionally refetches every completed game.

## Storage layout

```text
dashboard-data/
  seasons/
    2026/
      games/2026-03.jsonl
      appearances/2026-03.jsonl
      fetch-state.json
      next-games.json
      roster-pitchers.json
      manifest.json
```

Game and appearance records are partitioned monthly to keep machine-generated diffs small. Fetch state, upcoming schedules, and pitching roster context are stored separately from completed-game facts. The manifest records the schema version, coverage, API-call and failure counts, and SHA-256 hash of every data file.

The repository supports one current contract. Required files and fields are read directly; there are no compatibility paths for old snapshots because source and data are deployed together. A meaningful contract change must rebuild `dashboard-data` through the validated refresh workflow.

## Core semantics

- A team's pitches equal both `official_sp + official_rp` and `adjusted_sp + adjusted_rp`.
- Official SP/RP is MLB's per-game `gamesStarted` designation. A short or ineffective official start remains SP.
- Role adjustment is conservative and auditable. Ambiguous long relief remains RP with `needs_review`; reviewed exceptions use `config/role_overrides.json`.
- Every scheduled completed game is current, stale, or missing. A snapshot is complete only when all are current.
- A failed refetch preserves prior appearances as stale. A first-time failure is missing and is retried on the next refresh.
- A completed-game schedule that loses a previously persisted game is rejected.
- In-memory validation runs before writing; persisted reload then verifies structure, coverage, arithmetic, and manifest hashes before commit.

For the current calendar season, `roster-pitchers.json` combines MLB pitching depth-chart order with 40-man status. Depth roles are `SP`, `RP`, or closer `CP`. Status `A` is active; every other status becomes a compact availability badge for bullpen context. Historical seasons keep the required roster file empty and skip live roster/upcoming-game fetches.

## Browser exports

`pipeline.export` turns a validated snapshot into three build-time read models:

| Artifact | Contents |
| --- | --- |
| Season dashboard | Team totals, top-30 pitchers, team top-five usage by role framing, latest and next games, bullpen windows, and starter-rest context |
| Team timeseries | Daily team increments and game-grain complete games |
| Player history | Current top-30 pitchers across the selected season and three completed predecessors |

These payloads are intentionally smaller than the durable snapshot. The browser receives only what the UI renders and never receives a full appearance corpus.

### Season and player totals

Player totals follow `pitcher_id` across teams, so pre-trade appearances remain included. Current roster context supplies the displayed team when present; otherwise the latest appearance does. The current-season history total must equal the corresponding top-30 total.

Historical player series are sparse daily increments normalized to regular-season day zero. A season with no MLB appearances is exported as an explicit zero rather than omitted. Completed prior seasons retain both at-this-point and full-season totals; the active season has no full-season comparison.

Each team has top-five pitcher lists for total, official SP/RP, and adjusted SP/RP workload. Classification is per appearance, so a swingman may appear in both role lists.

### Team timelines and games

Daily timeseries metrics and game counts must sum to the season team row. Cumulative charts are prefix sums of those increments. Complete games remain at `(game_pk, team_id)` grain so a doubleheader cannot hide one inside a calendar-day total.

The latest available completed game is chosen from persisted appearances by MLB's scheduled `gameDate`, not `game_pk`, and carries the full matchup. On a partial snapshot this wording matters: the export does not imply that a missing newer game was fetched. Pitchers retain MLB appearance order.

The next-game export is the earliest non-final regular-season game in the schedule window. MLB may omit a probable starter; the UI reports that directly rather than inferring one. When announced, recent-start context uses official starts only. The rest-day flag comes from the full slate for the refresh's Eastern schedule date and is displayed only while that date is still today, preventing stale notices.

### Bullpen and starter context

Each team gets 14 ordered calendar dates ending with its latest available completed game. Pitch arrays align positionally with those dates and include official reliever pitches only; doubleheaders sum within a date. Active depth-chart relievers appear even with zero pitches. Non-active pitchers remain only when they worked during the window, retain their status badge and history, and sort below active arms.

A windowed reliever absent from the team's depth-chart and 40-man rows left that scope entirely — waivers, trade, outright, or release — and is badged `Gone` rather than shown as active. The badge asserts only 40-man absence as of the latest refresh; export never consults transaction history. When the pitcher surfaces on another team's roster snapshot, the description names the new organization. Historical seasons persist an empty roster snapshot and therefore carry no availability badges of any kind.

Within each availability group, sorting prioritizes latest-game relief pitches, then 3-, 5-, and 14-day totals, then name and id.

Starter rest contains active depth-chart SPs in MLB's published order. The last start follows `pitcher_id` across trades and counts only official starts. Days of rest are complete off-days between the start and as-of dates: `(as_of_date - last_start_date) - 1`, floored at zero. History stays null when the pitcher has no official start in the published season; export does not infer one or reach into an unvalidated season.

## Failure and ownership boundary

Per-game MLB failures may produce a valid partial snapshot, but structural corruption, arithmetic disagreement, schedule regression, or manifest mismatch prevents any commit. `Refresh dashboard data` is the only automated writer to the orphan `dashboard-data` branch. The Pages workflow consumes a specific validated data revision and publishes compiled output only as an ephemeral artifact.
