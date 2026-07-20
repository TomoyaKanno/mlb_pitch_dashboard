import type { Team } from "../api";
import {
  context,
  formatMetric,
  labels,
  metric,
  rawMetric,
  type Basis,
  type LeagueTotals,
  type Order,
  type View,
} from "../lib/metrics";

interface TeamTableProps {
  teams: Team[];
  league: LeagueTotals;
  view: View;
  basis: Basis;
  order: Order;
  perGame: boolean;
}

function rankAndOrder(teams: Team[], view: View, basis: Basis, order: Order) {
  // Rank is always by the raw (highest-first) metric so a team's rank number is
  // stable regardless of the chosen row order; ordering only re-sorts rows.
  const ranked = [...teams]
    .sort(
      (a, b) =>
        rawMetric(b, view, basis) - rawMetric(a, view, basis) ||
        a.team_name.localeCompare(b.team_name),
    )
    .map((team, index) => ({ team, rank: index + 1 }));

  if (order === "low") {
    return [...ranked].sort(
      (a, b) => rawMetric(a.team, view, basis) - rawMetric(b.team, view, basis),
    );
  }
  if (order === "alpha") {
    return [...ranked].sort((a, b) => a.team.team_name.localeCompare(b.team.team_name));
  }
  return ranked;
}

export function TeamTable({ teams, league, view, basis, order, perGame }: TeamTableProps) {
  const effectivePerGame = view === "share" ? false : perGame;
  const rows = rankAndOrder(teams, view, basis, order);
  const maximum = Math.max(
    ...rows.map((row) => Math.abs(metric(row.team, view, basis, effectivePerGame))),
    1,
  );

  return (
    <section className="table-shell">
      <table>
        <caption>All MLB teams ranked by the selected pitch-workload framing</caption>
        <thead>
          <tr>
            <th className="rank">Rank</th>
            <th>Team</th>
            <th id="metric-heading">{labels(view, effectivePerGame)}</th>
            <th className="context">Context</th>
          </tr>
        </thead>
        <tbody id="team-rows">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="empty">
                No cached data yet. Run a refresh to populate the dashboard.
              </td>
            </tr>
          ) : (
            rows.map(({ team, rank }) => {
              const value = metric(team, view, basis, effectivePerGame);
              const width = Math.max(2, (Math.abs(value) / maximum) * 100);
              return (
                <tr key={team.team_id}>
                  <td className="rank">{rank}</td>
                  <td className="team">{team.team_name}</td>
                  <td>
                    <div className="metric">
                      <strong>{formatMetric(value, view, effectivePerGame)}</strong>
                      <span className="track">
                        <span className="fill" style={{ width: `${width}%` }} />
                      </span>
                    </div>
                  </td>
                  <td className="context secondary">{context(team, league, view, basis)}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </section>
  );
}
