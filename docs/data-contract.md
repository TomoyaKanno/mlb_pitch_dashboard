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
      roster-pitchers.json
      manifest.json
```

Game and appearance records are partitioned by month to keep automated diffs small. Administrative fetch state, the current next-game read model, and pitching depth/40-man roster status are separate from baseball facts. The manifest identifies schema version 1, coverage, API calls, failures, and SHA-256 hashes for every data file.

Appearance records include both MLB's official `gamesStarted` designation and the conservative role-adjusted classification. A short, ineffective official start therefore remains an SP unless the established opener rules identify it as relief usage.

### `roster-pitchers.json`

For the current calendar season, refresh fetches each team's `rosterType=depthChart` and `rosterType=40Man` pitching rows and persists them as `RosterPitcherRecord`s:

- Depth-chart abbreviations map to `depth_role`: `SP`, bullpen `P` → `RP`, closer `CP`.
- Depth order preserves MLB's published order within the chart.
- Status codes come from MLB (`A`, `D10`/`D15`/`D60`, `RM`, …). Export maps those to compact `availability` badges (`IL`, `Minors`) for the bullpen UI and admits only active (`A`) depth-chart SPs to starter-rest context.
- Optional `jersey_number` is stored when MLB provides one. The current UI does not render jersey watermarks; the field remains available for a later presentation experiment.
- Historical seasons skip the roster fetch (empty file contents / empty snapshot map), matching upcoming-game behavior.

Legacy snapshots without `roster-pitchers.json` remain valid; export then falls back to appearance-only bullpen rows and an explicit empty starter-rest list for each team rather than inferring a current rotation from historical appearances.

## Browser-ready exports

`pipeline.export` projects the validated snapshot into static JSON consumed at Observable build time. These are read models, not a second source of truth:

| Artifact | Loader | Contents |
| --- | --- | --- |
| Season dashboard | `observable/src/data/dashboard.json.py` | One season-total row per team, the top 30 individual pitcher totals, per-team top-five pitcher usage lists for each role framing, one latest completed game, one upcoming-game record (optional probable starter with recent-start and rest-day context), one 14-day roster-aware bullpen-usage window, and one active-starter rest record per team |
| Team timeseries | `observable/src/data/team-timeseries.json.py` | Daily team increments for the timeline, plus game-grain `complete_games` (0 official RP, with pitcher) |
| Player history | `observable/src/data/player-history.json.py` | Sparse date-normalized pitch increments and season totals for the current top 30 player leaders across the configured season and its three completed predecessors; the Player total panel uses it for the workload-history chart and four-row comparison table |

Each `player_totals` row sums every persisted appearance for one `pitcher_id`, including appearances before a trade. When the current roster snapshot has that pitcher, it provides the displayed team/name; otherwise export falls back to the latest appearance. Rows are sorted by total pitches descending, then name and id, and capped at 30.

The player-history export deliberately does not ship every historical appearance to the browser. It loads the validated snapshots for `season - 3` through the configured season, then exports only the current top 30 `pitcher_id`s. Each historical season supplies a sparse sequence of per-date pitch increments normalized to regular-season day zero, a total, and appearance count. Missing MLB history is an explicit zero-total season, allowing the UI to distinguish a pitcher without demonstrated prior major-league workload from one with an established comparison range. The Player total panel shows the selected season’s total as its hero/current-table value and deliberately leaves that row’s full-season comparison visually blank; completed prior-season rows show both the selected-point and full-season totals. The current-season history total must exactly equal its `player_totals` row.

Each `team_pitcher_usage` row belongs to one team and contains a top-five list for `total`, `official_sp`, `official_rp`, `adjusted_sp`, and `adjusted_rp`. Each list sums only appearances for that team, ranks by its named metric (then pitcher name/id), and may contain fewer than five pitchers. Official and adjusted SP/RP are appearance-level classifications, so a swingman can appear in both SP and RP lists; the dashboard selects the list matching its current role basis.

Daily team points must reconcile to season team totals: summing each metric (and game counts) across dates for a team equals that team's dashboard row. The dashboard derives cumulative series with a prefix sum (`metricSeries`); daily/timecourse mode plots each day's increment (share uses that day's SP/RP split). Role adjustment has no timeline yet.

Recent games are selected at **game** grain. `GameRecord.game_datetime` stores MLB's scheduled `gameDate`, so a doubleheader chooses the later scheduled game even when its `game_pk` does not sort last. Old snapshots without this optional field use `game_pk` only until their next normal refresh rewrites the game records. Pitchers are ordered by `appearance_order` and may include an optional `jersey_number` from the roster snapshot.

Each `next_games` row is the earliest non-final regular-season game returned for a team in the 14-day schedule window. It also carries `schedule_date` and `is_rest_day_today`, computed during refresh from the entire regular-season slate for that date. A team with any game on the slate—including a final, postponed, cancelled, or suspended game—never receives the rest-day flag; this deliberately avoids an incorrect “rest day” claim after a same-day game or schedule disruption. The browser renders that flag only while `schedule_date` equals today in Eastern time, so a stale static snapshot does not persist yesterday’s notice. It includes the opponent and home/away context. MLB may omit a `probable_pitcher`; consumers must display that as unannounced rather than infer one. When a probable starter is present, the export also includes `probable_recent_starts` (up to three most recent official `gamesStarted` appearances with date, pitches, and opponent), `probable_days_rest` (calendar days between the latest of those starts and the upcoming game, minus one), and optional `probable_jersey_number`. Unannounced rows keep an empty start list and a null days-rest value. Existing snapshots created before this read model legitimately export an empty `next_games` list until their next successful refresh.

Each `bullpen_usage` row contains 14 unique, ordered calendar dates ending on that team's latest completed-game date. Pitch arrays align positionally with those dates and contain non-negative official-reliever pitch counts. Doubleheader appearances are summed into the same calendar-day cell; official starters are excluded. Depth-chart bullpen arms (`RP` / closer `CP`) are included even with zero pitches so unused active call-ups remain visible. IL and Minors arms with no in-window pitches are omitted; those badges appear only when the arm actually worked in the window. When `roster-pitchers.json` is present, each pitcher may also carry `on_depth_chart`, `depth_role`, `depth_order`, `availability`, and `status_description`. Legacy snapshots without roster data still export appearance-only rows with null roster fields. Rows first separate currently unavailable IL/Minors arms at the bottom. Within each group, pitchers who worked in the latest completed game sort by that game's relief pitches descending; remaining ties resolve by 3-, 5-, then 14-calendar-day totals, followed by name/id for stability.

Each `starter_rest` row belongs to one team and carries `as_of_date` plus the team's active MLB depth-chart starters. The as-of date uses the refresh's Eastern `schedule_date` when present and is never earlier than that team's latest completed game; legacy schedule records fall back to the latest completed-game date. Pitchers must have `depth_role=SP`, `status_code=A`, a non-negative `depth_order`, and a unique MLB player id within the team list. Rows preserve MLB's published depth-chart order instead of ranking or claiming fatigue/readiness.

For each listed starter, `last_start_date` and `last_start_pitches` come from that pitcher's latest official `gamesStarted` appearance in the season snapshot, keyed by pitcher id across teams so trades do not reset rest. Role-adjusted SP appearances do not count unless MLB also marked the appearance as an official start. `days_rest` is the number of complete calendar off-days between `last_start_date` and `as_of_date`: `(as_of_date - last_start_date) - 1`, floored at zero. The start date and as-of date are therefore both excluded, matching the probable-starter convention. All three history fields remain null when the pitcher has no official start in the published season; export does not reach into an unvalidated prior season or invent a value. Portraits remain display-only MLB CDN assets selected from `pitcher_id` in the browser.

Complete games are listed at **game** grain, not calendar day: a doubleheader can hide a CG inside a day total that still has RP pitches from the other game. Each `complete_games` row is a `(game_pk, team_id)` with zero official RP pitches and a single pitcher. Team timelines use this sibling export; player workload history is already delivered through the compact player-history export rather than a full appearance corpus.

## Failure behavior

- A failed first fetch is recorded as missing.
- A failed reconciliation fetch preserves the prior appearances and marks them stale.
- Per-game failures do not discard successful games from the same run.
- A schedule that loses a previously completed game is rejected as an unsafe regression.
- Structural errors such as missing teams, missing official starters, duplicate appearance order, or unclassified appearances prevent the snapshot from being written.

The scheduled `Refresh dashboard data` workflow commits only a validated snapshot to the orphan `dashboard-data` branch. A separate least-privilege workflow builds from that revision and gives GitHub Pages an ephemeral artifact.
