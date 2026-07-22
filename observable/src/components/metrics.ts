export type View = "total" | "sp" | "rp" | "share" | "adjustment" | "players";
export type Basis = "adjusted" | "official";
export type SortColumn = "metric" | "team";
export type SortDirection = "asc" | "desc";

export interface Team {
  team_id: number;
  team_name: string;
  games: number;
  total: number;
  official_sp: number;
  official_rp: number;
  adjusted_sp: number;
  adjusted_rp: number;
  bulk_to_sp: number;
  opener_to_rp: number;
  review_count: number;
}

export interface LeagueTotals {
  total: number;
  official_sp: number;
  official_rp: number;
  adjusted_sp: number;
  adjusted_rp: number;
  bulk_to_sp: number;
  opener_to_rp: number;
  review_count: number;
}

export interface RankedTeam {
  team: Team;
  rank: number;
}

export interface TeamDayPoint {
  date: string;
  team_id: number;
  team_name: string;
  games: number;
  total: number;
  official_sp: number;
  official_rp: number;
  adjusted_sp: number;
  adjusted_rp: number;
  bulk_to_sp: number;
  opener_to_rp: number;
  review_count: number;
}

export interface CumulativePoint {
  date: string;
  value: number;
}

export type SnapshotResult = "complete" | "partial" | "failed";

export interface CoverageStatus {
  result: SnapshotResult;
  scheduled_games: number;
  current_games: number;
  stale_games: number;
  missing_games: number;
}

const integer = new Intl.NumberFormat("en-US");
const decimal = new Intl.NumberFormat("en-US", {minimumFractionDigits: 1, maximumFractionDigits: 1});
const LEAGUE_KEYS = [
  "total", "official_sp", "official_rp", "adjusted_sp", "adjusted_rp",
  "bulk_to_sp", "opener_to_rp", "review_count",
] as const satisfies readonly (keyof LeagueTotals)[];

function roleKey(basis: Basis, role: "sp" | "rp"): keyof Team {
  return `${basis}_${role}` as keyof Team;
}

export function rawMetric(team: Team, view: View, basis: Basis): number {
  if (view === "total") return team.total;
  if (view === "sp" || view === "rp") return team[roleKey(basis, view)] as number;
  if (view === "share") return (team[roleKey(basis, "rp")] as number) / team.total;
  if (view === "players") return team.total;
  return team.adjusted_sp - team.official_sp;
}

export function metric(team: Team, view: View, basis: Basis, perGame: boolean): number {
  const value = rawMetric(team, view, basis);
  return perGame && view !== "share" ? value / team.games : value;
}

// Unweighted mean of the plotted metric across teams — the league-average
// bar length, used to place the "MLB average" notch on each bar.
export function averageMetric(teams: Team[], view: View, basis: Basis, perGame: boolean): number {
  if (teams.length === 0) return 0;
  const total = teams.reduce((sum, team) => sum + metric(team, view, basis, perGame), 0);
  return total / teams.length;
}

// Position of the MLB-average notch on the shared bar scale (0–100), matching
// how fill width uses abs(value) / maximum. Clamped so the marker stays on-track.
export function averageBarPercent(average: number, maximum: number): number {
  if (maximum <= 0) return 0;
  return Math.min(100, Math.max(0, (Math.abs(average) / maximum) * 100));
}

export type SeriesMode = "cumulative" | "daily";

// Role adjustment has no series chart yet.
export function seriesSupported(view: View): boolean {
  return view !== "adjustment" && view !== "players";
}

function teamDayRows(points: TeamDayPoint[], teamId: number): TeamDayPoint[] {
  return points
    .filter((point) => point.team_id === teamId)
    .sort((a, b) => a.date.localeCompare(b.date) || a.team_id - b.team_id);
}

function dayMetric(point: TeamDayPoint, view: View, basis: Basis): number {
  if (view === "total") return point.total;
  if (view === "sp" || view === "rp") return point[roleKey(basis, view)] as number;
  if (view === "share") {
    const rp = point[roleKey(basis, "rp")] as number;
    return point.total > 0 ? rp / point.total : 0;
  }
  if (view === "players") return point.total;
  return point.adjusted_sp - point.official_sp;
}

// Series for one team matching the table framing.
// cumulative: season-to-date running value (share = running RP/total).
// daily: each day's increment or that day's SP/RP split.
export function metricSeries(
  points: TeamDayPoint[],
  teamId: number,
  view: View,
  basis: Basis,
  mode: SeriesMode = "cumulative",
): CumulativePoint[] {
  if (!seriesSupported(view)) return [];
  const rows = teamDayRows(points, teamId);

  if (mode === "daily") {
    return rows.map((point) => ({date: point.date, value: dayMetric(point, view, basis)}));
  }

  if (view === "share") {
    const rpKey = roleKey(basis, "rp");
    let runningRp = 0;
    let runningTotal = 0;
    return rows.map((point) => {
      runningRp += point[rpKey] as number;
      runningTotal += point.total;
      return {
        date: point.date,
        value: runningTotal > 0 ? runningRp / runningTotal : 0,
      };
    });
  }

  let running = 0;
  return rows.map((point) => {
    running += dayMetric(point, view, basis);
    return {date: point.date, value: running};
  });
}

export function seriesTitle(view: View, basis: Basis, mode: SeriesMode = "cumulative"): string {
  const role = basis === "official" ? "official" : "adjusted";
  if (mode === "daily") {
    if (view === "total") return "Daily pitches";
    if (view === "sp") return `Daily ${role} SP pitches`;
    if (view === "rp") return `Daily ${role} RP pitches`;
    if (view === "share") return `Daily ${role} SP / RP split`;
    if (view === "players") return "Daily player pitches";
    return "Daily net SP reclassification";
  }
  if (view === "total") return "Cumulative pitches";
  if (view === "sp") return `Cumulative ${role} SP pitches`;
  if (view === "rp") return `Cumulative ${role} RP pitches`;
  if (view === "share") return `Season-to-date ${role} SP / RP split`;
  if (view === "players") return "Cumulative player pitches";
  return "Cumulative net SP reclassification";
}

export function formatSeriesValue(value: number, view: View): string {
  if (view === "share") return `${decimal.format(value * 100)}%`;
  const rounded = Math.round(value);
  if (view === "adjustment" && rounded > 0) return `+${integer.format(rounded)}`;
  return integer.format(rounded);
}

export interface DateDomain {
  start: string;
  end: string;
}

export function dateMs(date: string): number {
  const [year, month, day] = date.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

export interface CompleteGame {
  date: string;
  game_pk: number;
  team_id: number;
  team_name: string;
  pitches: number;
  pitcher_id: number;
  pitcher_name: string;
}

export function completeGamesForTeam(games: CompleteGame[], teamId: number): CompleteGame[] {
  return games
    .filter((game) => game.team_id === teamId)
    .sort((a, b) => a.date.localeCompare(b.date) || a.game_pk - b.game_pk);
}

const shortMonthDay = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export function formatCompleteGameDate(date: string): string {
  return shortMonthDay.format(new Date(dateMs(date)));
}

// Game-grain CGs from the export (not day rollups — doubleheaders keep each CG).
export function completeGameSummary(games: CompleteGame[]): string {
  if (games.length === 0) return "No complete games (0 official RP pitches) yet.";
  const labels = games.map((game) => {
    const when = formatCompleteGameDate(game.date);
    return `${when} ${game.pitcher_name}`;
  });
  return `Complete games (no RP): ${games.length} · ${labels.join(" · ")}`;
}

function formatUtcDate(ms: number): string {
  const date = new Date(ms);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// Shared season window for every team chart — min/max dates across the payload.
export function seriesDateDomain(points: Iterable<{date: string}>): DateDomain | null {
  let start = "";
  let end = "";
  for (const point of points) {
    if (!start || point.date < start) start = point.date;
    if (!end || point.date > end) end = point.date;
  }
  return start && end ? {start, end} : null;
}

export function dateToX(date: string, domain: DateDomain, left: number, width: number): number {
  const start = dateMs(domain.start);
  const span = dateMs(domain.end) - start || 1;
  return left + ((dateMs(date) - start) / span) * width;
}

// Nearest team day to the calendar date under the pointer (linear shared x-scale).
export function nearestSeriesIndexByDate(
  series: CumulativePoint[],
  domain: DateDomain,
  left: number,
  width: number,
  x: number,
): number {
  if (series.length === 0 || width <= 0) return -1;
  const start = dateMs(domain.start);
  const span = dateMs(domain.end) - start || 1;
  const clamped = Math.min(left + width, Math.max(left, x));
  const target = start + ((clamped - left) / width) * span;
  let best = 0;
  let bestDist = Infinity;
  for (let index = 0; index < series.length; index += 1) {
    const dist = Math.abs(dateMs(series[index].date) - target);
    if (dist < bestDist) {
      bestDist = dist;
      best = index;
    }
  }
  return best;
}

// One label per calendar month intersecting the shared domain.
// X sits at the midpoint of that month's visible span so partial opening
// months (e.g. Mar 26 start) do not collide with the next 1st.
export function monthAxisTicks(domain: DateDomain): {date: string; label: string}[] {
  const month = new Intl.DateTimeFormat("en-US", {month: "short", timeZone: "UTC"});
  const startMs = dateMs(domain.start);
  const endMs = dateMs(domain.end);
  let year = Number(domain.start.slice(0, 4));
  let monthIndex = Number(domain.start.slice(5, 7)) - 1;
  const ticks: {date: string; label: string}[] = [];
  while (true) {
    const firstOfMonth = Date.UTC(year, monthIndex, 1);
    const nextMonth = Date.UTC(year, monthIndex + 1, 1);
    if (firstOfMonth > endMs) break;
    const visibleStart = Math.max(firstOfMonth, startMs);
    const visibleEnd = Math.min(nextMonth - 86_400_000, endMs);
    if (visibleStart > visibleEnd) break;
    const mid = visibleStart + (visibleEnd - visibleStart) / 2;
    ticks.push({date: formatUtcDate(Math.round(mid)), label: month.format(firstOfMonth)});
    monthIndex += 1;
    if (monthIndex === 12) {
      monthIndex = 0;
      year += 1;
    }
  }
  return ticks;
}

export function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const fraction = value / exp;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * exp;
}

export function valueAxisTicks(min: number, max: number, view: View): number[] {
  if (view === "share") return [0, 0.25, 0.5, 0.75, 1];
  const top = niceCeil(Math.max(max, min, 1));
  if (top <= 0) return [0];
  return [0, top / 2, top];
}

export function seriesTooltipText(point: CumulativePoint, view: View): string {
  if (view === "share") {
    const rp = formatSeriesValue(point.value, view);
    const sp = formatSeriesValue(1 - point.value, view);
    return `${point.date} · ${sp} SP · ${rp} RP`;
  }
  return `${point.date} · ${formatSeriesValue(point.value, view)}`;
}

// Header-click sort: same column toggles direction; a new column uses its default
// (metric → highest first, team → A–Z).
export function nextSort(
  column: SortColumn,
  direction: SortDirection,
  clicked: SortColumn,
): {column: SortColumn; direction: SortDirection} {
  if (clicked === column) {
    return {column: clicked, direction: direction === "asc" ? "desc" : "asc"};
  }
  return {column: clicked, direction: clicked === "metric" ? "desc" : "asc"};
}

export function rankTeams(
  teams: Team[],
  view: View,
  basis: Basis,
  sortColumn: SortColumn,
  sortDirection: SortDirection,
  perGame: boolean,
): RankedTeam[] {
  const value = (team: Team) => metric(team, view, basis, perGame);
  // Ranks always follow the metric (highest = 1), independent of display order.
  const ranked = [...teams]
    .sort((a, b) => value(b) - value(a) || a.team_name.localeCompare(b.team_name))
    .map((team, index) => ({team, rank: index + 1}));

  if (sortColumn === "team") {
    const dir = sortDirection === "asc" ? 1 : -1;
    return [...ranked].sort(
      (a, b) => dir * a.team.team_name.localeCompare(b.team.team_name),
    );
  }
  if (sortDirection === "asc") {
    return [...ranked].sort(
      (a, b) => value(a.team) - value(b.team) || a.team.team_name.localeCompare(b.team.team_name),
    );
  }
  return ranked;
}

export function formatMetric(value: number, view: View, perGame: boolean): string {
  if (view === "share") return `${decimal.format(value * 100)}%`;
  if (perGame) return decimal.format(value);
  const rounded = Math.round(value);
  if (view === "adjustment" && rounded > 0) return `+${integer.format(rounded)}`;
  return integer.format(rounded);
}

function signed(value: number): string {
  if (Math.abs(value) < 0.05) return "0.0";
  return `${value > 0 ? "+" : "−"}${decimal.format(Math.abs(value))}`;
}

export function leagueTotals(teams: Team[]): LeagueTotals {
  const sums: LeagueTotals = {
    total: 0, official_sp: 0, official_rp: 0, adjusted_sp: 0,
    adjusted_rp: 0, bulk_to_sp: 0, opener_to_rp: 0, review_count: 0,
  };
  for (const team of teams) {
    for (const key of LEAGUE_KEYS) sums[key] += Number(team[key] || 0);
  }
  return sums;
}

export function context(team: Team, league: LeagueTotals, view: View, basis: Basis): string {
  if (view === "total") {
    return `${decimal.format((team.adjusted_sp / team.total) * 100)}% SP · ${decimal.format((team.adjusted_rp / team.total) * 100)}% RP`;
  }
  if (view === "sp" || view === "rp") {
    const key = roleKey(basis, view) as keyof LeagueTotals;
    const share = (team[key] as number) / team.total;
    return `${decimal.format(share * 100)}% of team total · ${signed((share - league[key] / league.total) * 100)} pp vs MLB`;
  }
  if (view === "share") {
    const key = roleKey(basis, "rp") as keyof LeagueTotals;
    const share = (team[key] as number) / team.total;
    return `${decimal.format((1 - share) * 100)}% SP · ${signed((share - league[key] / league.total) * 100)} pp vs MLB`;
  }
  return `${integer.format(team.bulk_to_sp)} bulk → SP · ${integer.format(team.opener_to_rp)} opener → RP`;
}

export function label(view: View, perGame: boolean): string {
  const suffix = perGame && view !== "share" ? " per game" : "";
  if (view === "total") return `Total pitches${suffix}`;
  if (view === "sp") return `SP pitches${suffix}`;
  if (view === "rp") return `RP pitches${suffix}`;
  if (view === "share") return "Bullpen share";
  if (view === "players") return "Player total pitches";
  return `Net SP reclassification${suffix}`;
}

// Tone class for a snapshot result. The values are namespaced (status-*)
// on purpose: a bare "warning" collides with Observable Framework's built-in
// .warning callout class, which injects a heading label and border.
export function statusTone(result: SnapshotResult): "" | "status-warning" | "status-failed" {
  if (result === "failed") return "status-failed";
  if (result === "partial") return "status-warning";
  return "";
}

export function statusLabel(result: SnapshotResult): string {
  if (result === "complete") return "Validated snapshot";
  return `${result[0].toUpperCase()}${result.slice(1)} snapshot`;
}

export function coverageText(status: CoverageStatus): string {
  const base = `${integer.format(status.current_games)} / ${integer.format(status.scheduled_games)}`;
  const extra = [
    status.stale_games ? `${integer.format(status.stale_games)} stale` : "",
    status.missing_games ? `${integer.format(status.missing_games)} missing` : "",
  ].filter(Boolean).join(" · ");
  return extra ? `${base} · ${extra}` : base;
}
