export type View = "total" | "sp" | "rp" | "share" | "adjustment";
export type Basis = "adjusted" | "official";
export type Order = "high" | "low" | "alpha";

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
  return team.adjusted_sp - team.official_sp;
}

export function metric(team: Team, view: View, basis: Basis, perGame: boolean): number {
  const value = rawMetric(team, view, basis);
  return perGame && view !== "share" ? value / team.games : value;
}

export function rankTeams(
  teams: Team[],
  view: View,
  basis: Basis,
  order: Order,
  perGame: boolean,
): RankedTeam[] {
  const value = (team: Team) => metric(team, view, basis, perGame);
  const ranked = [...teams]
    .sort((a, b) => value(b) - value(a) || a.team_name.localeCompare(b.team_name))
    .map((team, index) => ({team, rank: index + 1}));

  if (order === "low") {
    return [...ranked].sort(
      (a, b) => value(a.team) - value(b.team) || a.team.team_name.localeCompare(b.team.team_name),
    );
  }
  if (order === "alpha") {
    return [...ranked].sort((a, b) => a.team.team_name.localeCompare(b.team.team_name));
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
