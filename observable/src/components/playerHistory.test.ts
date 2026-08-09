import {describe, expect, it} from "vitest";
import {
  playerCurve, playerValueAt, priorSeasonEnvelope,
  type PlayerHistoryPoint, type PlayerHistorySeason,
} from "./playerHistory";

function season(points: PlayerHistoryPoint[], seasonDays = 110, seasonYear = 2025): PlayerHistorySeason {
  return {
    season: seasonYear,
    season_days: seasonDays,
    total: points.reduce((total, point) => total + point.pitches, 0),
    appearances: points.length,
    points,
  };
}

describe("player history curves", () => {
  it("builds a step curve that only rises on game days", () => {
    const s = season([{day: 20, pitches: 50}, {day: 85, pitches: 30}]);
    expect(playerCurve(s)).toEqual([
      {day: 0, value: 0},
      {day: 20, value: 0},
      {day: 20, value: 50},
      {day: 85, value: 50},
      {day: 85, value: 80},
      {day: 110, value: 80},
    ]);
  });

  it("does not duplicate the closing point when the last game is on the final day", () => {
    const s = season([{day: 110, pitches: 40}]);
    expect(playerCurve(s)).toEqual([
      {day: 0, value: 0},
      {day: 110, value: 0},
      {day: 110, value: 40},
    ]);
  });

  it("draws a zero-MLB season as a flat line across the whole season", () => {
    expect(playerCurve(season([], 183))).toEqual([
      {day: 0, value: 0},
      {day: 183, value: 0},
    ]);
  });

  it("reads the cumulative total at a day with game-day boundaries inclusive", () => {
    const s = season([{day: 20, pitches: 50}, {day: 85, pitches: 30}]);
    expect(playerValueAt(s, 19)).toBe(0);
    expect(playerValueAt(s, 20)).toBe(50);
    expect(playerValueAt(s, 84)).toBe(50);
    expect(playerValueAt(s, 85)).toBe(80);
    expect(playerValueAt(s, 200)).toBe(80);
  });
});

describe("prior-season envelope", () => {
  const early = season([{day: 10, pitches: 20}], 100, 2023);
  const late = season([{day: 30, pitches: 40}], 90, 2024);

  it("steps vertically on game days instead of ramping before them", () => {
    const envelope = priorSeasonEnvelope([early, late], 100);
    const atTen = envelope.filter((point) => point.day === 10);
    // Before early's day-10 game both seasons sit at zero; after it the
    // envelope opens to [0, 20] at the same x position.
    expect(atTen).toEqual([
      {day: 10, low: 0, high: 0},
      {day: 10, low: 0, high: 20},
    ]);
    const atThirty = envelope.filter((point) => point.day === 30);
    expect(atThirty).toEqual([
      {day: 30, low: 0, high: 20},
      {day: 30, low: 20, high: 40},
    ]);
  });

  it("covers day zero through the shared max day in order", () => {
    const envelope = priorSeasonEnvelope([early, late], 100);
    // 0, both game days, both season ends, and maxDay — one before/after pair each.
    expect(envelope.map((point) => point.day)).toEqual([0, 0, 10, 10, 30, 30, 90, 90, 100, 100]);
    expect(envelope[0]).toEqual({day: 0, low: 0, high: 0});
    expect(envelope[envelope.length - 1]).toEqual({day: 100, low: 20, high: 40});
    const days = envelope.map((point) => point.day);
    expect(days).toEqual([...days].sort((a, b) => a - b));
  });

  it("stays flat at zero for pitchers with no prior MLB workload", () => {
    const envelope = priorSeasonEnvelope([season([], 100, 2023)], 100);
    expect(envelope.every((point) => point.low === 0 && point.high === 0)).toBe(true);
  });
});
