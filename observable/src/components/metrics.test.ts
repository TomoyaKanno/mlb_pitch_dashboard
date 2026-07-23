import {describe, expect, it} from "vitest";
import {
  averageBarPercent, averageMetric, completeGamesForTeam, completeGameSummary, coverageText,
  formatSeriesValue, metricSeries, leagueTotals, metric, monthAxisTicks, nearestSeriesIndexByDate,
  nextSort, niceCeil, rankTeams, rawMetric, seriesDateDomain, seriesSupported, seriesTitle,
  seriesTooltipText, statusLabel, statusTone, valueAxisTicks, type CompleteGame, type CoverageStatus,
  type Team, type TeamDayPoint,
  BULLPEN_TOTAL_WINDOWS, trailingPitchTotal,
} from "./metrics";

const team: Team = {
  team_id: 119,
  team_name: "Los Angeles Dodgers",
  games: 100,
  total: 15_000,
  official_sp: 8_400,
  official_rp: 6_600,
  adjusted_sp: 8_900,
  adjusted_rp: 6_100,
  bulk_to_sp: 600,
  opener_to_rp: 100,
  review_count: 2,
};

describe("static dashboard metrics", () => {
  it("sums trailing calendar-day relief pitches for the heatmap totals", () => {
    const pitches = [3, 0, 11, 5, 0, 22, 7, 4, 0, 16, 9, 0, 18, 6];

    expect(BULLPEN_TOTAL_WINDOWS).toEqual([3, 5, 14]);
    expect(trailingPitchTotal(pitches, 3)).toBe(24);
    expect(trailingPitchTotal(pitches, 5)).toBe(49);
    expect(trailingPitchTotal(pitches, 14)).toBe(101);
    expect(trailingPitchTotal([8, 0], 5)).toBe(8);
    expect(trailingPitchTotal(pitches, 0)).toBe(0);
  });

  it("switches between official and adjusted role totals", () => {
    expect(rawMetric(team, "sp", "official")).toBe(8_400);
    expect(rawMetric(team, "sp", "adjusted")).toBe(8_900);
    expect(rawMetric(team, "rp", "adjusted")).toBe(6_100);
  });

  it("normalizes count metrics per game without changing shares", () => {
    expect(metric(team, "total", "adjusted", true)).toBe(150);
    expect(metric(team, "share", "adjusted", true)).toBeCloseTo(6_100 / 15_000);
  });

  it("ranks by the displayed per-game metric", () => {
    const highVolume = {...team, team_id: 120, team_name: "High Volume", games: 4, total: 200};
    const highRate = {...team, team_id: 121, team_name: "High Rate", games: 1, total: 100};

    expect(rankTeams([highVolume, highRate], "total", "adjusted", "metric", "desc", false))
      .toEqual([
        {team: highVolume, rank: 1},
        {team: highRate, rank: 2},
      ]);
    expect(rankTeams([highVolume, highRate], "total", "adjusted", "metric", "desc", true))
      .toEqual([
        {team: highRate, rank: 1},
        {team: highVolume, rank: 2},
      ]);
  });

  it("averages the plotted metric across teams", () => {
    const a = {...team, team_id: 120, total: 10_000, games: 100, adjusted_rp: 4_000};
    const b = {...team, team_id: 121, total: 20_000, games: 100, adjusted_rp: 8_000};

    // Unweighted mean of totals: (10k + 20k) / 2.
    expect(averageMetric([a, b], "total", "adjusted", false)).toBe(15_000);
    // Per game divides each team by its own games before averaging.
    expect(averageMetric([a, b], "total", "adjusted", true)).toBe(150);
    // Mean of per-team bullpen shares: (0.40 + 0.40) / 2.
    expect(averageMetric([a, b], "share", "adjusted", false)).toBeCloseTo(0.4);
    expect(averageMetric([], "total", "adjusted", false)).toBe(0);
  });

  it("places the MLB-average notch on the shared bar scale", () => {
    expect(averageBarPercent(7_500, 15_000)).toBe(50);
    expect(averageBarPercent(-3_000, 10_000)).toBe(30);
    expect(averageBarPercent(12_000, 10_000)).toBe(100);
    expect(averageBarPercent(1_000, 0)).toBe(0);
  });

  it("keeps metric ranks when rows are reordered", () => {
    const first = {...team, team_id: 120, team_name: "Alpha", total: 100};
    const second = {...team, team_id: 121, team_name: "Zulu", total: 200};

    expect(rankTeams([first, second], "total", "adjusted", "team", "asc", false)
      .map(({team: row, rank}) => [row.team_name, rank]))
      .toEqual([["Alpha", 2], ["Zulu", 1]]);
    expect(rankTeams([first, second], "total", "adjusted", "team", "desc", false)
      .map(({team: row, rank}) => [row.team_name, rank]))
      .toEqual([["Zulu", 1], ["Alpha", 2]]);
    expect(rankTeams([first, second], "total", "adjusted", "metric", "asc", false)
      .map(({team: row, rank}) => [row.team_name, rank]))
      .toEqual([["Alpha", 2], ["Zulu", 1]]);
  });

  it("toggles sort direction on the active column and defaults a new column", () => {
    expect(nextSort("metric", "desc", "metric")).toEqual({column: "metric", direction: "asc"});
    expect(nextSort("metric", "asc", "metric")).toEqual({column: "metric", direction: "desc"});
    expect(nextSort("metric", "desc", "team")).toEqual({column: "team", direction: "asc"});
    expect(nextSort("team", "asc", "metric")).toEqual({column: "metric", direction: "desc"});
  });

  it("sums league summary fields", () => {
    const doubled = leagueTotals([team, {...team, team_id: 120}]);
    expect(doubled.total).toBe(30_000);
    expect(doubled.adjusted_sp).toBe(17_800);
    expect(doubled.review_count).toBe(4);
  });

  it("builds cumulative and daily series for the selected framing", () => {
    const points: TeamDayPoint[] = [
      {
        date: "2026-04-02", team_id: 119, team_name: "Los Angeles Dodgers", games: 1,
        total: 100, official_sp: 60, official_rp: 40, adjusted_sp: 70, adjusted_rp: 30,
        bulk_to_sp: 10, opener_to_rp: 0, review_count: 0,
      },
      {
        date: "2026-04-01", team_id: 119, team_name: "Los Angeles Dodgers", games: 1,
        total: 80, official_sp: 50, official_rp: 30, adjusted_sp: 45, adjusted_rp: 35,
        bulk_to_sp: 0, opener_to_rp: 5, review_count: 0,
      },
      {
        date: "2026-04-01", team_id: 147, team_name: "New York Yankees", games: 1,
        total: 90, official_sp: 55, official_rp: 35, adjusted_sp: 55, adjusted_rp: 35,
        bulk_to_sp: 0, opener_to_rp: 0, review_count: 0,
      },
    ];
    expect(metricSeries(points, 119, "total", "adjusted", "cumulative")).toEqual([
      {date: "2026-04-01", value: 80},
      {date: "2026-04-02", value: 180},
    ]);
    expect(metricSeries(points, 119, "total", "adjusted", "daily")).toEqual([
      {date: "2026-04-01", value: 80},
      {date: "2026-04-02", value: 100},
    ]);
    expect(metricSeries(points, 119, "sp", "adjusted", "cumulative")).toEqual([
      {date: "2026-04-01", value: 45},
      {date: "2026-04-02", value: 115},
    ]);
    expect(metricSeries(points, 119, "rp", "official", "daily")).toEqual([
      {date: "2026-04-01", value: 30},
      {date: "2026-04-02", value: 40},
    ]);
    expect(metricSeries(points, 119, "share", "adjusted", "cumulative")).toEqual([
      {date: "2026-04-01", value: 35 / 80},
      {date: "2026-04-02", value: 65 / 180},
    ]);
    expect(metricSeries(points, 119, "share", "adjusted", "daily")).toEqual([
      {date: "2026-04-01", value: 35 / 80},
      {date: "2026-04-02", value: 30 / 100},
    ]);
    expect(metricSeries(points, 119, "adjustment", "adjusted", "cumulative")).toEqual([]);
    expect(seriesSupported("adjustment")).toBe(false);
    expect(seriesSupported("share")).toBe(true);
    expect(metricSeries(points, 999, "total", "adjusted", "daily")).toEqual([]);
    expect(seriesTitle("share", "adjusted", "cumulative")).toBe("Season-to-date adjusted SP / RP split");
    expect(seriesTitle("share", "adjusted", "daily")).toBe("Daily adjusted SP / RP split");
    expect(formatSeriesValue(0.401, "share")).toBe("40.1%");
  });

  it("uses a shared linear date domain for every team chart", () => {
    expect(seriesDateDomain([])).toBeNull();
    expect(seriesDateDomain([
      {date: "2026-04-02"},
      {date: "2026-03-26"},
      {date: "2026-07-19"},
    ])).toEqual({start: "2026-03-26", end: "2026-07-19"});
  });

  it("maps pointer x to the nearest day on the shared calendar scale", () => {
    const domain = {start: "2026-03-01", end: "2026-07-01"};
    const series = [
      {date: "2026-03-01", value: 1},
      {date: "2026-05-01", value: 2},
      {date: "2026-07-01", value: 3},
    ];
    expect(nearestSeriesIndexByDate([], domain, 0, 400, 10)).toBe(-1);
    expect(nearestSeriesIndexByDate(series, domain, 0, 400, 0)).toBe(0);
    expect(nearestSeriesIndexByDate(series, domain, 0, 400, 400)).toBe(2);
    expect(nearestSeriesIndexByDate(series, domain, 0, 400, 200)).toBe(1);
  });

  it("labels each month once on the shared x-axis", () => {
    const ticks = monthAxisTicks({start: "2026-03-26", end: "2026-07-19"});
    expect(ticks.map((tick) => tick.label)).toEqual(["Mar", "Apr", "May", "Jun", "Jul"]);
    // Partial March is labeled near its visible midpoint, not jammed on the 1st.
    expect(ticks[0]?.date).toBe("2026-03-28");
    expect(ticks[1]?.date).toBe("2026-04-15");
  });

  it("builds tidy y-axis ticks", () => {
    expect(niceCeil(15_450)).toBe(20_000);
    expect(valueAxisTicks(0, 15_450, "total")).toEqual([0, 10_000, 20_000]);
    expect(valueAxisTicks(0, 1, "share")).toEqual([0, 0.25, 0.5, 0.75, 1]);
  });

  it("formats series tooltip copy for pitch and share views", () => {
    expect(seriesTooltipText({date: "2026-04-01", value: 1234}, "total")).toBe("2026-04-01 · 1,234");
    expect(seriesTooltipText({date: "2026-04-01", value: 0.403}, "share"))
      .toBe("2026-04-01 · 59.7% SP · 40.3% RP");
  });

  it("summarizes game-grain complete games with pitchers", () => {
    const games: CompleteGame[] = [
      {
        date: "2026-04-01", game_pk: 1, team_id: 119, team_name: "Dodgers",
        pitches: 98, pitcher_id: 1, pitcher_name: "Yamamoto",
      },
      {
        date: "2026-07-19", game_pk: 10, team_id: 119, team_name: "Dodgers",
        pitches: 108, pitcher_id: 1, pitcher_name: "Yamamoto",
      },
      {
        date: "2026-07-19", game_pk: 11, team_id: 147, team_name: "Yankees",
        pitches: 99, pitcher_id: 2, pitcher_name: "Cole",
      },
    ];
    expect(completeGamesForTeam(games, 119)).toHaveLength(2);
    expect(completeGameSummary(completeGamesForTeam(games, 119)))
      .toBe("Complete games (no RP): 2 · Apr 1 Yamamoto · Jul 19 Yamamoto");
    expect(completeGameSummary([])).toBe("No complete games (0 official RP pitches) yet.");
  });
});

describe("snapshot status presentation", () => {
  const complete: CoverageStatus = {
    result: "complete", scheduled_games: 1_490, current_games: 1_490,
    stale_games: 0, missing_games: 0,
  };

  it("labels each snapshot result", () => {
    expect(statusLabel("complete")).toBe("Validated snapshot");
    expect(statusLabel("partial")).toBe("Partial snapshot");
    expect(statusLabel("failed")).toBe("Failed snapshot");
  });

  it("uses namespaced tone classes so they cannot collide with Observable's .warning callout", () => {
    expect(statusTone("complete")).toBe("");
    expect(statusTone("partial")).toBe("status-warning");
    expect(statusTone("failed")).toBe("status-failed");
    // A bare "warning"/"failed" would trigger Observable Framework's built-in
    // callout styling; assert the namespaced prefix stays in place.
    expect(statusTone("partial")).not.toBe("warning");
    expect(statusTone("failed")).not.toBe("failed");
  });

  it("shows plain coverage when every game is current", () => {
    expect(coverageText(complete)).toBe("1,490 / 1,490");
  });

  it("appends stale and missing counts only when nonzero", () => {
    expect(coverageText({...complete, result: "partial", current_games: 1_472, stale_games: 12, missing_games: 6}))
      .toBe("1,472 / 1,490 · 12 stale · 6 missing");
    expect(coverageText({...complete, result: "partial", current_games: 1_478, stale_games: 12}))
      .toBe("1,478 / 1,490 · 12 stale");
    expect(coverageText({...complete, result: "partial", current_games: 1_484, missing_games: 6}))
      .toBe("1,484 / 1,490 · 6 missing");
  });
});
