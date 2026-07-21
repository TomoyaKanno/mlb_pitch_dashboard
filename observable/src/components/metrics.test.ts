import {describe, expect, it} from "vitest";
import {
  averageBarPercent, averageMetric, coverageText, leagueTotals, metric, nextSort, rankTeams, rawMetric,
  statusLabel, statusTone, type CoverageStatus, type Team,
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
