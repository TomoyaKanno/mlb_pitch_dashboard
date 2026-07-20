import {describe, expect, it} from "vitest";
import {leagueTotals, metric, rawMetric, type Team} from "./metrics";

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

  it("sums league summary fields", () => {
    const doubled = leagueTotals([team, {...team, team_id: 120}]);
    expect(doubled.total).toBe(30_000);
    expect(doubled.adjusted_sp).toBe(17_800);
    expect(doubled.review_count).toBe(4);
  });
});
