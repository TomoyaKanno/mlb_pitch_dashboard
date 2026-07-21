import {useMemo, useState} from "npm:react";
import {
  context, formatMetric, label, leagueTotals, metric, rankTeams,
  type Basis, type LeagueTotals, type Order, type Team, type View,
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

function StatusStrip({data}: {data: DashboardData}) {
  const status = data.status;
  const tone = status.result === "failed" ? "failed" : status.result === "partial" ? "warning" : "";
  const prefix = status.result === "complete" ? "Validated snapshot" : `${status.result[0].toUpperCase()}${status.result.slice(1)} snapshot`;
  const coverage = [
    status.stale_games ? `${integer.format(status.stale_games)} stale` : "",
    status.missing_games ? `${integer.format(status.missing_games)} missing` : "",
  ].filter(Boolean).join(" · ");
  return (
    <section className={`status-strip${tone ? ` ${tone}` : ""}`} aria-live="polite">
      <span>{prefix}</span>
      <span>
        {integer.format(status.current_games)}/{integer.format(status.scheduled_games)} games
        {coverage ? ` · ${coverage}` : ""} · {integer.format(status.api_calls)} API calls
      </span>
    </section>
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

function TeamTable({teams, league, view, basis, order, perGame}: {
  teams: Team[]; league: LeagueTotals; view: View; basis: Basis; order: Order; perGame: boolean;
}) {
  const effectivePerGame = view === "share" ? false : perGame;
  const rows = rankTeams(teams, view, basis, order, effectivePerGame);
  const maximum = Math.max(...rows.map(({team}) => Math.abs(metric(team, view, basis, effectivePerGame))), 1);
  return (
    <section className="table-shell">
      <table>
        <caption>All MLB teams ranked by the selected pitch-workload framing</caption>
        <thead><tr><th className="rank">Rank</th><th>Team</th><th>{label(view, effectivePerGame)}</th><th className="context">Context</th></tr></thead>
        <tbody>
          {rows.map(({team, rank}) => {
            const value = metric(team, view, basis, effectivePerGame);
            const width = Math.max(2, Math.abs(value) / maximum * 100);
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
                <td><div className="metric"><strong>{formatMetric(value, view, effectivePerGame)}</strong><span className="track"><span className="fill" style={{width: `${width}%`}} /></span></div></td>
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
  const [order, setOrder] = useState<Order>("high");
  const [perGame, setPerGame] = useState(false);
  const league = useMemo(() => leagueTotals(data.teams), [data.teams]);
  const roleView = view === "sp" || view === "rp" || view === "share";
  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">MLB season workload</p>
          <h1>Who has thrown the most pitches?</h1>
          <p className="lede">Compare total, starter, and bullpen workloads with an auditable adjustment for openers and bulk appearances.</p>
        </div>
        <div className="snapshot-panel">
          <span>Season</span><strong>{data.season}</strong>
          <span>Data source</span><strong>Validated static snapshot</strong>
          <span>Updated</span><strong>{new Date(data.generated_at).toLocaleString()}</strong>
        </div>
      </header>
      <StatusStrip data={data} />
      <LeagueGrid league={league} />
      <section className="controls" aria-label="Table controls">
        <div className="framing">
          {FRAMINGS.map((item) => <button key={item.view} type="button" className={view === item.view ? "active" : undefined} onClick={() => setView(item.view)}>{item.label}</button>)}
        </div>
        {roleView && <label>Role basis<select value={basis} onChange={(event) => setBasis(event.target.value as Basis)}><option value="adjusted">Role-adjusted</option><option value="official">Official appearance</option></select></label>}
        <label>Order<select value={order} onChange={(event) => setOrder(event.target.value as Order)}><option value="high">Highest first</option><option value="low">Lowest first</option><option value="alpha">Team A–Z</option></select></label>
        {view !== "share" && <label className="check"><input type="checkbox" checked={perGame} onChange={(event) => setPerGame(event.target.checked)} />Per game</label>}
      </section>
      <TeamTable teams={data.teams} league={league} view={view} basis={basis} order={order} perGame={perGame} />
      <footer>
        Official appearance uses MLB’s per-game starter flag. Role-adjusted classifications preserve true starters behind openers while flagging ambiguous long outings for review.
        {data.data_commit ? <> Data revision <code>{data.data_commit.slice(0, 8)}</code>.</> : null}
      </footer>
    </main>
  );
}
