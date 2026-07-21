import {useMemo, useState} from "npm:react";
import {
  averageBarPercent, averageMetric, context, coverageText, formatMetric, label,
  leagueTotals, metric, nextSort, rankTeams, statusLabel, statusTone,
  type Basis, type LeagueTotals, type SortColumn, type SortDirection, type Team, type View,
} from "./metrics.js";

interface Status {
  result: "complete" | "partial" | "failed";
  api_calls: number;
  games_requested: number;
  games_fetched: number;
  games_failed: number;
  scheduled_games: number;
  current_games: number;
  stale_games: number;
  missing_games: number;
}

interface DashboardData {
  schema_version: number;
  season: number;
  generated_at: string;
  code_commit: string | null;
  data_commit: string | null;
  status: Status;
  teams: Team[];
}

const integer = new Intl.NumberFormat("en-US");
const decimal = new Intl.NumberFormat("en-US", {minimumFractionDigits: 1, maximumFractionDigits: 1});
const FRAMINGS: {view: View; label: string}[] = [
  {view: "total", label: "Total"},
  {view: "sp", label: "SP workload"},
  {view: "rp", label: "RP workload"},
  {view: "share", label: "Bullpen share"},
  {view: "adjustment", label: "Role adjustment"},
];

function ariaSort(
  active: SortColumn,
  column: SortColumn,
  direction: SortDirection,
): "ascending" | "descending" | "none" {
  if (active !== column) return "none";
  return direction === "asc" ? "ascending" : "descending";
}

function SnapshotPanel({data}: {data: DashboardData}) {
  const status = data.status;
  const tone = statusTone(status.result);
  const coverageTone = status.stale_games || status.missing_games ? tone || undefined : undefined;
  return (
    <aside className="snapshot-panel" aria-label="Snapshot diagnostics">
      <div><span>Season</span><strong>{data.season}</strong></div>
      <div><span>Status</span><strong className={tone || undefined} aria-live="polite">{statusLabel(status.result)}</strong></div>
      <div><span>Games</span><strong className={coverageTone}>{coverageText(status)}</strong></div>
      <div><span>API calls</span><strong>{integer.format(status.api_calls)}</strong></div>
      <div><span>Updated</span><strong>{new Date(data.generated_at).toLocaleString()}</strong></div>
    </aside>
  );
}

function LeagueGrid({league}: {league: LeagueTotals}) {
  return (
    <section className="league-grid" aria-label="League summary">
      <div><strong>{league.total ? integer.format(league.total) : "—"}</strong><span>Total pitches</span></div>
      <div><strong>{league.total ? `${decimal.format((league.adjusted_sp / league.total) * 100)}%` : "—"}</strong><span>Adjusted SP share</span></div>
      <div><strong>{integer.format(league.bulk_to_sp + league.opener_to_rp)}</strong><span>Reclassified pitches</span></div>
      <div><strong>{integer.format(league.review_count)}</strong><span>Appearances to review</span></div>
    </section>
  );
}

function SortHeader({
  column, label: text, sortColumn, sortDirection, onSort,
}: {
  column: SortColumn;
  label: string;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  onSort: (column: SortColumn) => void;
}) {
  const active = sortColumn === column;
  return (
    <th className="sortable" aria-sort={ariaSort(sortColumn, column, sortDirection)}>
      <button type="button" onClick={() => onSort(column)}>
        {text}
        {active ? (
          <span className="sort-indicator" aria-hidden="true">
            {sortDirection === "asc" ? "↑" : "↓"}
          </span>
        ) : null}
      </button>
    </th>
  );
}

function TeamTable({teams, league, view, basis, sortColumn, sortDirection, perGame, onSort}: {
  teams: Team[];
  league: LeagueTotals;
  view: View;
  basis: Basis;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  perGame: boolean;
  onSort: (column: SortColumn) => void;
}) {
  const effectivePerGame = view === "share" ? false : perGame;
  const rows = rankTeams(teams, view, basis, sortColumn, sortDirection, effectivePerGame);
  const maximum = Math.max(...rows.map(({team}) => Math.abs(metric(team, view, basis, effectivePerGame))), 1);
  const average = averageMetric(teams, view, basis, effectivePerGame);
  const averagePercent = averageBarPercent(average, maximum);
  return (
    <section className="table-shell">
      <table>
        <caption>All MLB teams ranked by the selected pitch-workload framing</caption>
        <thead>
          <tr>
            <th className="rank">Rank</th>
            <SortHeader column="team" label="Team" sortColumn={sortColumn} sortDirection={sortDirection} onSort={onSort} />
            <SortHeader
              column="metric"
              label={label(view, effectivePerGame)}
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <th className="context">Context</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({team, rank}) => {
            const value = metric(team, view, basis, effectivePerGame);
            const width = Math.max(2, Math.abs(value) / maximum * 100);
            const splitTotal = view === "total" && team.total > 0;
            const spShare = splitTotal ? (team.adjusted_sp / team.total) * 100 : 0;
            return (
              <tr key={team.team_id}>
                <td className="rank">{rank}</td>
                <td className="team">
                  <span className="team-name">
                    <img
                      className="team-logo"
                      src={`https://www.mlbstatic.com/team-logos/${team.team_id}.svg`}
                      alt=""
                      width={22}
                      height={22}
                      loading="lazy"
                      onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
                    />
                    {team.team_name}
                  </span>
                </td>
                <td>
                  <div className="metric">
                    <strong>{formatMetric(value, view, effectivePerGame)}</strong>
                    <span className="track">
                      <span className="fill" style={{width: `${width}%`}}>
                        {splitTotal ? (
                          <>
                            <span className="fill-sp" style={{width: `${spShare}%`}} />
                            <span className="fill-rp" />
                          </>
                        ) : null}
                      </span>
                      <span
                        className="avg-notch"
                        style={{left: `${averagePercent}%`}}
                        title="MLB average"
                        aria-hidden="true"
                      />
                    </span>
                  </div>
                </td>
                <td className="context secondary">{context(team, league, view, basis)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function Dashboard({data}: {data: DashboardData}) {
  const [view, setView] = useState<View>("total");
  const [basis, setBasis] = useState<Basis>("adjusted");
  const [sortColumn, setSortColumn] = useState<SortColumn>("metric");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [perGame, setPerGame] = useState(false);
  const league = useMemo(() => leagueTotals(data.teams), [data.teams]);
  const roleView = view === "sp" || view === "rp" || view === "share";

  function handleSort(column: SortColumn) {
    const next = nextSort(sortColumn, sortDirection, column);
    setSortColumn(next.column);
    setSortDirection(next.direction);
  }

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">MLB season workload</p>
        <h1>Who has thrown the most pitches?</h1>
        <p className="lede">Compare total, starter, and bullpen workloads with an auditable adjustment for openers and bulk appearances.</p>
      </header>
      <LeagueGrid league={league} />
      <section className="controls" aria-label="Table controls">
        <div className="framing">
          {FRAMINGS.map((item) => <button key={item.view} type="button" className={view === item.view ? "active" : undefined} onClick={() => setView(item.view)}>{item.label}</button>)}
        </div>
        {roleView && <label>Role basis<select value={basis} onChange={(event) => setBasis(event.target.value as Basis)}><option value="adjusted">Role-adjusted</option><option value="official">Official appearance</option></select></label>}
        {view !== "share" && <label className="check"><input type="checkbox" checked={perGame} onChange={(event) => setPerGame(event.target.checked)} />Per game</label>}
      </section>
      <TeamTable
        teams={data.teams}
        league={league}
        view={view}
        basis={basis}
        sortColumn={sortColumn}
        sortDirection={sortDirection}
        perGame={perGame}
        onSort={handleSort}
      />
      <footer>
        Official appearance uses MLB’s per-game starter flag. Role-adjusted classifications preserve true starters behind openers while flagging ambiguous long outings for review.
        {data.data_commit ? <> Data revision <code>{data.data_commit.slice(0, 8)}</code>.</> : null}
      </footer>
      <SnapshotPanel data={data} />
    </main>
  );
}
