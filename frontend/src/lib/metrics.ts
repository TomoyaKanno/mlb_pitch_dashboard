// Pure metric helpers ported from the original vanilla dashboard. They take the
// current framing (view/basis/perGame) explicitly instead of reading a global,
// so they are trivially unit-testable and reusable across future pages.
import type { Team } from "../api";
import { decimal, integer } from "./format";

export type View = "total" | "sp" | "rp" | "share" | "adjustment";
export type Basis = "adjusted" | "official";
export type Order = "high" | "low" | "alpha";

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

const LEAGUE_KEYS = [
  "total",
  "official_sp",
  "official_rp",
  "adjusted_sp",
  "adjusted_rp",
  "bulk_to_sp",
  "opener_to_rp",
  "review_count",
] as const satisfies readonly (keyof LeagueTotals)[];

function roleKey(basis: Basis, role: "sp" | "rp"): keyof Team {
  return `${basis}_${role}` as keyof Team;
}

/** The unnormalized value used for ranking (never per-game). */
export function rawMetric(team: Team, view: View, basis: Basis): number {
  switch (view) {
    case "total":
      return team.total;
    case "sp":
      return team[roleKey(basis, "sp")] as number;
    case "rp":
      return team[roleKey(basis, "rp")] as number;
    case "share":
      return (team[roleKey(basis, "rp")] as number) / team.total;
    case "adjustment":
      return team.adjusted_sp - team.official_sp;
  }
}

/** The displayed value, optionally normalized to a per-game rate. */
export function metric(team: Team, view: View, basis: Basis, perGame: boolean): number {
  const value = rawMetric(team, view, basis);
  return perGame && view !== "share" ? value / team.games : value;
}

export function formatMetric(value: number, view: View, perGame: boolean): string {
  if (view === "share") return `${decimal.format(value * 100)}%`;
  if (perGame) return decimal.format(value);
  const rounded = Math.round(value);
  if (view === "adjustment" && rounded > 0) return `+${integer.format(rounded)}`;
  return integer.format(rounded);
}

export function signed(value: number): string {
  if (Math.abs(value) < 0.05) return "0.0";
  return `${value > 0 ? "+" : "−"}${decimal.format(Math.abs(value))}`;
}

export function leagueTotals(teams: Team[]): LeagueTotals {
  const sums: LeagueTotals = {
    total: 0,
    official_sp: 0,
    official_rp: 0,
    adjusted_sp: 0,
    adjusted_rp: 0,
    bulk_to_sp: 0,
    opener_to_rp: 0,
    review_count: 0,
  };
  for (const team of teams) {
    for (const key of LEAGUE_KEYS) {
      sums[key] += Number(team[key] || 0);
    }
  }
  return sums;
}

export function context(team: Team, league: LeagueTotals, view: View, basis: Basis): string {
  if (view === "total") {
    return `${decimal.format((team.adjusted_sp / team.total) * 100)}% SP · ${decimal.format(
      (team.adjusted_rp / team.total) * 100,
    )}% RP`;
  }
  if (view === "sp" || view === "rp") {
    const key = roleKey(basis, view) as keyof LeagueTotals;
    const share = (team[key] as number) / team.total;
    const leagueShare = league[key] / league.total;
    return `${decimal.format(share * 100)}% of team total · ${signed(
      (share - leagueShare) * 100,
    )} pp vs MLB`;
  }
  if (view === "share") {
    const key = roleKey(basis, "rp") as keyof LeagueTotals;
    const share = (team[key] as number) / team.total;
    const leagueShare = league[key] / league.total;
    return `${decimal.format((1 - share) * 100)}% SP · ${signed((share - leagueShare) * 100)} pp vs MLB`;
  }
  return `${integer.format(team.bulk_to_sp)} bulk → SP · ${integer.format(
    team.opener_to_rp,
  )} opener → RP`;
}

export function labels(view: View, perGame: boolean): string {
  const suffix = perGame && view !== "share" ? " per game" : "";
  if (view === "total") return `Total pitches${suffix}`;
  if (view === "sp") return `SP pitches${suffix}`;
  if (view === "rp") return `RP pitches${suffix}`;
  if (view === "share") return "Bullpen share";
  return `Net SP reclassification${suffix}`;
}
