export interface PlayerHistoryPoint {
  day: number;
  pitches: number;
}

export interface PlayerHistorySeason {
  season: number;
  season_days: number;
  total: number;
  appearances: number;
  points: PlayerHistoryPoint[];
}

export interface PlayerHistory {
  pitcher_id: number;
  pitcher_name: string;
  seasons: PlayerHistorySeason[];
}

export interface PlayerHistoryData {
  schema_version: number;
  season: number;
  historical_seasons: number[];
  players: PlayerHistory[];
}

export interface PlayerCurvePoint {
  day: number;
  value: number;
}

// Step curve of cumulative pitches: flat between game days, vertical on them,
// held flat out to the end of the regular season.
export function playerCurve(season: PlayerHistorySeason): PlayerCurvePoint[] {
  const curve: PlayerCurvePoint[] = [{day: 0, value: 0}];
  let total = 0;
  for (const point of season.points) {
    curve.push({day: point.day, value: total});
    total += point.pitches;
    curve.push({day: point.day, value: total});
  }
  if (curve[curve.length - 1].day !== season.season_days) {
    curve.push({day: season.season_days, value: total});
  }
  return curve;
}

export function playerValueAt(season: PlayerHistorySeason, day: number): number {
  let total = 0;
  for (const point of season.points) {
    if (point.day > day) break;
    total += point.pitches;
  }
  return total;
}

export interface EnvelopePoint {
  day: number;
  low: number;
  high: number;
}

// Min/max envelope across the prior seasons' cumulative curves. Each game day
// keeps both its before and after values so the envelope changes vertically,
// like the individual step curves, rather than ramping before a pitcher has
// actually thrown the pitches.
export function priorSeasonEnvelope(
  prior: PlayerHistorySeason[],
  maxDay: number,
): EnvelopePoint[] {
  const days = Array.from(new Set([
    0,
    maxDay,
    ...prior.flatMap((season) => [season.season_days, ...season.points.map((point) => point.day)]),
  ])).sort((a, b) => a - b);
  return days.flatMap((day) => {
    const before = prior.map((season) => playerValueAt(season, day - 1));
    const after = prior.map((season) => playerValueAt(season, day));
    return [
      {day, low: Math.min(...before), high: Math.max(...before)},
      {day, low: Math.min(...after), high: Math.max(...after)},
    ];
  });
}
