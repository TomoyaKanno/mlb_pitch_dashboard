import {useEffect, useMemo, useRef, useState} from "npm:react";
import {
  averageBarPercent, averageMetric, context, coverageText, formatMetric, formatSeriesValue,
  label, leagueTotals, metric, metricSeries, nextSort, rankTeams, seriesSupported, seriesTitle,
  statusLabel, statusTone,
  type Basis, type CumulativePoint, type LeagueTotals, type SeriesMode, type SortColumn,
  type SortDirection, type Team, type TeamDayPoint, type View,
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

interface TeamTimeseriesData {
  schema_version: number;
  season: number;
  points: TeamDayPoint[];
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

function pointX(index: number, count: number, width: number): number {
  return count === 1 ? width / 2 : (index / (count - 1)) * width;
}

function seriesPath(
  series: CumulativePoint[],
  width: number,
  height: number,
  domain: {min: number; max: number} = {min: Math.min(0, ...series.map((point) => point.value)), max: Math.max(...series.map((point) => point.value), 1)},
): string {
  if (series.length === 0) return "";
  const span = domain.max - domain.min || 1;
  return series.map((point, index) => {
    const x = pointX(index, series.length, width);
    const y = height - ((point.value - domain.min) / span) * height;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

function shareAreas(
  series: CumulativePoint[],
  width: number,
  height: number,
): {rp: string; sp: string; line: string} {
  // Share series value is season-to-date RP share (0–1). Shade below = RP, above = SP.
  const line = seriesPath(series, width, height, {min: 0, max: 1});
  if (series.length === 0) return {rp: "", sp: "", line: ""};
  const firstX = pointX(0, series.length, width).toFixed(1);
  const lastX = pointX(series.length - 1, series.length, width).toFixed(1);
  return {
    line,
    rp: `${line} L${lastX} ${height} L${firstX} ${height} Z`,
    sp: `${line} L${lastX} 0 L${firstX} 0 Z`,
  };
}

function TeamSeriesPanel({
  team, series, view, basis, mode, contextText, onModeChange, onClose,
}: {
  team: Team;
  series: CumulativePoint[];
  view: View;
  basis: Basis;
  mode: SeriesMode;
  contextText: string;
  onModeChange: (mode: SeriesMode) => void;
  onClose: () => void;
}) {
  const width = 320;
  const height = 160;
  const first = series[0];
  const last = series[series.length - 1];
  const share = view === "share" ? shareAreas(series, width, height) : null;
  const path = share ? share.line : seriesPath(series, width, height);
  const title = seriesTitle(view, basis, mode);
  const copyRef = useRef<HTMLDivElement>(null);
  const [badgePx, setBadgePx] = useState(64);
  useEffect(() => {
    const el = copyRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const sync = () => setBadgePx(Math.max(48, Math.round(el.getBoundingClientRect().height)));
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [title, team.team_name, contextText]);
  return (
    <aside className="team-series-panel" aria-label={`${team.team_name} pitch timeline`}>
      <div className="team-series-header">
        <div className="team-series-identity">
          <div
            className="team-series-badge-slot"
            aria-hidden="true"
            style={{width: badgePx, height: badgePx}}
          >
            <img
              className="team-series-badge"
              src={`https://www.mlbstatic.com/team-logos/${team.team_id}.svg`}
              alt=""
              loading="lazy"
              onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
            />
          </div>
          <div className="team-series-copy" ref={copyRef}>
            <p className="team-series-kicker">{title}</p>
            <h2 className="team-series-title">{team.team_name}</h2>
            <p className="secondary team-series-context">{contextText}</p>
          </div>
        </div>
        <button type="button" className="team-series-close" onClick={onClose}>Close</button>
      </div>
      <label className="team-series-mode">
        Series
        <select value={mode} onChange={(event) => onModeChange(event.target.value as SeriesMode)}>
          <option value="cumulative">Cumulative</option>
          <option value="daily">Timecourse (daily)</option>
        </select>
      </label>
      {series.length === 0 ? (
        <p className="secondary">No dated pitch points for this team.</p>
      ) : (
        <>
          <svg
            className={`team-series-chart${share ? " share-chart" : ""}`}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={title}
          >
            {share ? (
              <>
                <path className="series-sp-area" d={share.sp} />
                <path className="series-rp-area" d={share.rp} />
              </>
            ) : null}
            <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
          </svg>
          {share ? (
            <p className="secondary team-series-legend">
              <span className="legend-sp">SP above</span>
              <span aria-hidden="true"> · </span>
              <span className="legend-rp">RP below</span>
            </p>
          ) : null}
          <p className="secondary team-series-meta">
            {first.date} → {last.date} · {formatSeriesValue(last.value, view)}
            {view === "share" ? " RP" : ""}
            {mode === "daily" ? " (latest day)" : ""} · {series.length} days
          </p>
        </>
      )}
    </aside>
  );
}

function TeamTable({
  teams, league, view, basis, sortColumn, sortDirection, perGame, selectedTeamId, seriesEnabled, showContext, onSort, onSelectTeam,
}: {
  teams: Team[];
  league: LeagueTotals;
  view: View;
  basis: Basis;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  perGame: boolean;
  selectedTeamId: number | null;
  seriesEnabled: boolean;
  showContext: boolean;
  onSort: (column: SortColumn) => void;
  onSelectTeam: (teamId: number) => void;
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
            {showContext ? <th className="context">Context</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map(({team, rank}) => {
            const value = metric(team, view, basis, effectivePerGame);
            const width = Math.max(2, Math.abs(value) / maximum * 100);
            const splitTotal = view === "total" && team.total > 0;
            const spShare = splitTotal ? (team.adjusted_sp / team.total) * 100 : 0;
            const selected = selectedTeamId === team.team_id;
            return (
              <tr key={team.team_id} className={selected ? "selected" : undefined}>
                <td className="rank">{rank}</td>
                <td className="team">
                  <button
                    type="button"
                    className="team-select"
                    aria-pressed={selected}
                    disabled={!seriesEnabled}
                    title={seriesEnabled ? undefined : "Timeline unavailable for this framing"}
                    onClick={() => onSelectTeam(team.team_id)}
                  >
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
                  </button>
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
                {showContext ? <td className="context secondary">{context(team, league, view, basis)}</td> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function Dashboard({
  data, timeseries,
}: {
  data: DashboardData;
  timeseries: TeamTimeseriesData;
}) {
  const [view, setView] = useState<View>("total");
  const [basis, setBasis] = useState<Basis>("adjusted");
  const [sortColumn, setSortColumn] = useState<SortColumn>("metric");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [perGame, setPerGame] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [seriesMode, setSeriesMode] = useState<SeriesMode>("cumulative");
  const league = useMemo(() => leagueTotals(data.teams), [data.teams]);
  const roleView = view === "sp" || view === "rp" || view === "share";
  const selectedTeam = data.teams.find((team) => team.team_id === selectedTeamId) ?? null;
  const selectedSeries = useMemo(
    () => (selectedTeamId == null ? [] : metricSeries(timeseries.points, selectedTeamId, view, basis, seriesMode)),
    [timeseries.points, selectedTeamId, view, basis, seriesMode],
  );

  function handleSort(column: SortColumn) {
    const next = nextSort(sortColumn, sortDirection, column);
    setSortColumn(next.column);
    setSortDirection(next.direction);
  }

  function handleView(next: View) {
    setView(next);
    if (!seriesSupported(next)) setSelectedTeamId(null);
  }

  function handleSelectTeam(teamId: number) {
    if (!seriesSupported(view)) return;
    setSelectedTeamId((current) => (current === teamId ? null : teamId));
  }

  const showSeries = selectedTeam != null && seriesSupported(view);

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
          {FRAMINGS.map((item) => <button key={item.view} type="button" className={view === item.view ? "active" : undefined} onClick={() => handleView(item.view)}>{item.label}</button>)}
        </div>
        {roleView && <label>Role basis<select value={basis} onChange={(event) => setBasis(event.target.value as Basis)}><option value="adjusted">Role-adjusted</option><option value="official">Official appearance</option></select></label>}
        {view !== "share" && <label className="check"><input type="checkbox" checked={perGame} onChange={(event) => setPerGame(event.target.checked)} />Per game</label>}
      </section>
      <div className={showSeries ? "table-with-panel" : undefined}>
        <TeamTable
          teams={data.teams}
          league={league}
          view={view}
          basis={basis}
          sortColumn={sortColumn}
          sortDirection={sortDirection}
          perGame={perGame}
          selectedTeamId={showSeries ? selectedTeamId : null}
          seriesEnabled={seriesSupported(view)}
          showContext={!showSeries}
          onSort={handleSort}
          onSelectTeam={handleSelectTeam}
        />
        {showSeries && selectedTeam ? (
          <TeamSeriesPanel
            team={selectedTeam}
            series={selectedSeries}
            view={view}
            basis={basis}
            mode={seriesMode}
            contextText={context(selectedTeam, league, view, basis)}
            onModeChange={setSeriesMode}
            onClose={() => setSelectedTeamId(null)}
          />
        ) : null}
      </div>
      <footer>
        Official appearance uses MLB’s per-game starter flag. Role-adjusted classifications preserve true starters behind openers while flagging ambiguous long outings for review.
        {data.data_commit ? <> Data revision <code>{data.data_commit.slice(0, 8)}</code>.</> : null}
      </footer>
      <SnapshotPanel data={data} />
    </main>
  );
}
