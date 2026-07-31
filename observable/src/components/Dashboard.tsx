import {useEffect, useMemo, useRef, useState} from "npm:react";
import {
  averageBarPercent, averageMetric, completeGamesForTeam, completeGameSummary, context, coverageText,
  dateToX, formatMetric, formatSeriesValue, label, leagueTotals, metric, metricSeries,
  monthAxisTicks, nearestSeriesIndexByDate, nextSort, niceCeil, rankTeams, seriesDateDomain,
  seriesSupported, seriesTitle, seriesTooltipText, statusLabel, statusTone, valueAxisTicks,
  type Basis, type CompleteGame, type CumulativePoint, type DateDomain, type LeagueTotals,
  type SeriesMode, type SortColumn, type SortDirection, type Team, type TeamDayPoint, type View,
} from "./metrics.js";
import {
  RecentStrain, type BullpenUsage, type NextTeamGame, type RecentTeamGame, type StarterRest,
} from "./RecentStrain.js";

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
  player_totals: PlayerTotal[];
  team_pitcher_usage: TeamPitcherUsage[];
  recent_games: RecentTeamGame[];
  next_games: NextTeamGame[];
  bullpen_usage: BullpenUsage[];
  starter_rest: StarterRest[];
}

interface PlayerTotal {
  pitcher_id: number;
  pitcher_name: string;
  team_id: number;
  team_name: string;
  total: number;
}

interface PlayerHistoryPoint {
  day: number;
  pitches: number;
}

interface PlayerHistorySeason {
  season: number;
  season_days: number;
  total: number;
  appearances: number;
  points: PlayerHistoryPoint[];
}

interface PlayerHistory {
  pitcher_id: number;
  pitcher_name: string;
  seasons: PlayerHistorySeason[];
}

interface PlayerHistoryData {
  schema_version: number;
  season: number;
  historical_seasons: number[];
  players: PlayerHistory[];
}

interface PitcherUsage {
  pitcher_id: number;
  pitcher_name: string;
  total: number;
  official_sp: number;
  official_rp: number;
  adjusted_sp: number;
  adjusted_rp: number;
}

interface TeamPitcherUsage {
  team_id: number;
  team_name: string;
  total: PitcherUsage[];
  official_sp: PitcherUsage[];
  official_rp: PitcherUsage[];
  adjusted_sp: PitcherUsage[];
  adjusted_rp: PitcherUsage[];
}

interface TeamTimeseriesData {
  schema_version: number;
  season: number;
  points: TeamDayPoint[];
  complete_games: CompleteGame[];
}

const integer = new Intl.NumberFormat("en-US");
const decimal = new Intl.NumberFormat("en-US", {minimumFractionDigits: 1, maximumFractionDigits: 1});

const teamAbbreviations: Record<number, string> = {
  108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN",
  114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KC", 119: "LAD",
  120: "WSH", 121: "NYM", 133: "ATH", 134: "PIT", 135: "SD", 136: "SEA",
  137: "SF", 138: "STL", 139: "TB", 140: "TEX", 141: "TOR", 142: "MIN",
  143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
};

function teamAbbreviation(teamId: number, teamName: string): string {
  return teamAbbreviations[teamId]
    ?? teamName.split(/\s+/).map((word) => word[0]).join("").slice(0, 3).toUpperCase();
}

const FRAMINGS: {view: View; label: string}[] = [
  {view: "total", label: "Team total"},
  {view: "sp", label: "SP workload"},
  {view: "rp", label: "RP workload"},
  {view: "share", label: "Bullpen share"},
  {view: "adjustment", label: "Role adjustment"},
  {view: "players", label: "Player total"},
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

function seriesValueDomain(
  series: CumulativePoint[],
  view: View,
): {min: number; max: number} {
  if (view === "share") return {min: 0, max: 1};
  const values = series.map((point) => point.value);
  return {
    min: Math.min(0, ...values),
    max: niceCeil(Math.max(...values, 1)),
  };
}

function pointY(value: number, domain: {min: number; max: number}, top: number, height: number): number {
  const span = domain.max - domain.min || 1;
  return top + height - ((value - domain.min) / span) * height;
}

function seriesPath(
  series: CumulativePoint[],
  dateDomain: DateDomain,
  valueDomain: {min: number; max: number},
  plot: {left: number; top: number; width: number; height: number},
): string {
  if (series.length === 0) return "";
  return series.map((point, index) => {
    const x = dateToX(point.date, dateDomain, plot.left, plot.width);
    const y = pointY(point.value, valueDomain, plot.top, plot.height);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

function shareAreas(
  series: CumulativePoint[],
  dateDomain: DateDomain,
  plot: {left: number; top: number; width: number; height: number},
): {rp: string; sp: string; line: string} {
  // Share series value is season-to-date RP share (0–1). Shade below = RP, above = SP.
  const valueDomain = {min: 0, max: 1};
  const line = seriesPath(series, dateDomain, valueDomain, plot);
  if (series.length === 0) return {rp: "", sp: "", line: ""};
  const firstX = dateToX(series[0].date, dateDomain, plot.left, plot.width).toFixed(1);
  const lastX = dateToX(series[series.length - 1].date, dateDomain, plot.left, plot.width).toFixed(1);
  const bottom = plot.top + plot.height;
  const top = plot.top;
  return {
    line,
    rp: `${line} L${lastX} ${bottom} L${firstX} ${bottom} Z`,
    sp: `${line} L${lastX} ${top} L${firstX} ${top} Z`,
  };
}

function chartPointerX(event: {currentTarget: SVGSVGElement; clientX: number}, width: number): number {
  const rect = event.currentTarget.getBoundingClientRect();
  if (rect.width <= 0) return 0;
  return ((event.clientX - rect.left) / rect.width) * width;
}

function formatAxisValue(value: number, view: View): string {
  if (view === "share") return `${Math.round(value * 100)}%`;
  if (value >= 1000) return `${Math.round(value / 1000)}k`;
  return integer.format(Math.round(value));
}

interface PlayerCurvePoint { day: number; value: number }

function playerCurve(season: PlayerHistorySeason): PlayerCurvePoint[] {
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

function playerValueAt(season: PlayerHistorySeason, day: number): number {
  let total = 0;
  for (const point of season.points) {
    if (point.day > day) break;
    total += point.pitches;
  }
  return total;
}

function numericPath(
  series: PlayerCurvePoint[],
  maxDay: number,
  valueMax: number,
  plot: {left: number; top: number; width: number; height: number},
): string {
  return series.map((point, index) => {
    const x = plot.left + (point.day / maxDay) * plot.width;
    const y = pointY(point.value, {min: 0, max: valueMax}, plot.top, plot.height);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
}

function PlayerHistoryPanel({
  pitcher, history, onClose,
}: {
  pitcher: PlayerTotal;
  history: PlayerHistory;
  onClose: () => void;
}) {
  const width = 520;
  const height = 268;
  const plot = {left: 42, top: 16, width: 464, height: 176};
  const current = history.seasons[history.seasons.length - 1];
  const prior = history.seasons.slice(0, -1);
  const lastYear = prior[prior.length - 1];
  const maxDay = Math.max(...history.seasons.map((season) => season.season_days), 1);
  const currentDay = current.season_days;
  const priorMlbSeasons = prior.filter((season) => season.total > 0).length;
  const bandDays = Array.from(new Set([
    0,
    maxDay,
    ...prior.flatMap((season) => [season.season_days, ...season.points.map((point) => point.day)]),
  ])).sort((a, b) => a - b);
  const band = bandDays.flatMap((day) => {
    // Retain both sides of each game date so the envelope changes vertically,
    // like the individual cumulative pitch curves, rather than ramping before
    // a pitcher has actually thrown the pitches.
    const before = prior.map((season) => playerValueAt(season, day - 1));
    const after = prior.map((season) => playerValueAt(season, day));
    return [
      {day, low: Math.min(...before), high: Math.max(...before)},
      {day, low: Math.min(...after), high: Math.max(...after)},
    ];
  });
  const valueMax = niceCeil(Math.max(
    pitcher.total,
    ...history.seasons.map((season) => season.total),
  ));
  const yTicks = valueAxisTicks(0, valueMax, "total");
  const currentPath = numericPath(playerCurve(current), maxDay, valueMax, plot);
  const lastYearPath = numericPath(playerCurve(lastYear), maxDay, valueMax, plot);
  const bandPath = `${band.map((point, index) => {
    const x = plot.left + (point.day / maxDay) * plot.width;
    const y = pointY(point.high, {min: 0, max: valueMax}, plot.top, plot.height);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ")} ${band.slice().reverse().map((point) => {
    const x = plot.left + (point.day / maxDay) * plot.width;
    const y = pointY(point.low, {min: 0, max: valueMax}, plot.top, plot.height);
    return `L${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ")} Z`;
  const currentX = plot.left + (currentDay / maxDay) * plot.width;

  return (
    <aside className="team-series-panel is-open player-history-panel" aria-label={`${pitcher.pitcher_name} workload history`}>
      <div className="team-series-header">
        <div className="team-series-identity">
          <img
            className="pitcher-portrait player-history-portrait"
            src={`https://img.mlbstatic.com/mlb-photos/image/upload/w_128,d_people:generic:headshot:67:current.png,q_auto:best,f_auto/v1/people/${pitcher.pitcher_id}/headshot/67/current`}
            alt=""
            width={48}
            height={64}
            onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
          />
          <div className="team-series-copy">
            <p className="team-series-kicker">Player workload history</p>
            <h2 className="team-series-title">{pitcher.pitcher_name}</h2>
            <p className="secondary team-series-context">{pitcher.team_name} · cumulative pitches by regular-season day</p>
          </div>
        </div>
        <button type="button" className="team-series-close" onClick={onClose}>Close</button>
      </div>
      <div className="player-history-total" aria-label={`${current.season} current pitch total`}>
        <span>{current.season} current pitches</span>
        <strong>{integer.format(pitcher.total)}</strong>
      </div>
      <p className="player-history-availability">
        {priorMlbSeasons === 0
          ? "No MLB pitch workload in the prior three completed seasons."
          : `${priorMlbSeasons} of 3 prior completed seasons included MLB pitch workload.`}
      </p>
      <div className="team-series-chart-wrap">
        <svg className="team-series-chart player-history-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${pitcher.pitcher_name} current workload compared with the prior three completed seasons`}>
          {yTicks.map((tick) => {
            const y = pointY(tick, {min: 0, max: valueMax}, plot.top, plot.height);
            return <g key={tick}><line className="series-grid" x1={plot.left} x2={plot.left + plot.width} y1={y} y2={y} /><text className="series-axis-label" x={plot.left - 6} y={y} textAnchor="end" dominantBaseline="middle">{formatAxisValue(tick, "total")}</text></g>;
          })}
          <line className="series-axis" x1={plot.left} x2={plot.left} y1={plot.top} y2={plot.top + plot.height} />
          <line className="series-axis" x1={plot.left} x2={plot.left + plot.width} y1={plot.top + plot.height} y2={plot.top + plot.height} />
          <path className="player-history-band" d={bandPath} />
          <path className="player-history-last-year" d={lastYearPath} />
          <path className="player-history-current" d={currentPath} />
          <line className="player-history-today" x1={currentX} x2={currentX} y1={plot.top} y2={plot.top + plot.height} />
          <text className="series-axis-label" x={plot.left} y={plot.top + plot.height + 16} textAnchor="start">Opening day</text>
          <text className="series-axis-label" x={plot.left + plot.width / 2} y={plot.top + plot.height + 16} textAnchor="middle">Midseason</text>
          <text className="series-axis-label" x={plot.left + plot.width} y={plot.top + plot.height + 16} textAnchor="end">Regular-season end</text>
        </svg>
      </div>
      <div className="player-history-legend" aria-label="Chart legend">
        <span><i className="legend-current" />{current.season} current</span>
        <span><i className="legend-last-year" />{lastYear.season}</span>
        <span><i className="legend-band" />{prior[0].season}–{lastYear.season} range</span>
      </div>
      <table className="player-history-season-summary">
        <thead>
          <tr><th scope="col">Season</th><th scope="col">At this point</th><th scope="col">Full season</th></tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">{current.season}</th>
            <td>{integer.format(pitcher.total)}</td>
            <td aria-label="Full-season comparison is not shown for the selected season" />
          </tr>
          {prior.slice().reverse().map((season) => (
            <tr key={season.season}>
              <th scope="row">{season.season}</th>
              <td>{integer.format(playerValueAt(season, currentDay))}</td>
              <td>{integer.format(season.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  );
}

type PitcherUsageKey = "total" | "official_sp" | "official_rp" | "adjusted_sp" | "adjusted_rp";

function pitcherUsageKey(view: View, basis: Basis): PitcherUsageKey | null {
  if (view === "total") return "total";
  if (view === "sp") return basis === "official" ? "official_sp" : "adjusted_sp";
  if (view === "rp") return basis === "official" ? "official_rp" : "adjusted_rp";
  return null;
}

function pitcherUsageMeta(view: View, basis: Basis, pitcher: PitcherUsage): string {
  if (view === "total") {
    return `${integer.format(pitcher.adjusted_sp)} adjusted SP · ${integer.format(pitcher.adjusted_rp)} adjusted RP`;
  }
  return basis === "official" ? "Official appearance designation" : "Role-adjusted classification";
}

function TeamPitcherUsageList({
  usage, view, basis,
}: {
  usage: TeamPitcherUsage | null;
  view: View;
  basis: Basis;
}) {
  const key = pitcherUsageKey(view, basis);
  if (usage == null || key == null) return null;

  const pitchers = usage[key];
  const title = view === "total"
    ? "Top 5 pitcher usage"
    : `Top 5 ${basis === "official" ? "official" : "role-adjusted"} ${view.toUpperCase()} workloads`;
  return (
    <section className="team-pitcher-usage" aria-label={title}>
      <div className="team-pitcher-usage-header">
        <h3>{title}</h3>
        <span>{view === "total" ? "All pitches" : "Season to date"}</span>
      </div>
      {pitchers.length ? (
        <ol className="team-pitcher-usage-list">
          {pitchers.map((pitcher) => (
            <li className="team-pitcher-usage-row" key={pitcher.pitcher_id}>
              <img
                className="pitcher-portrait"
                src={`https://img.mlbstatic.com/mlb-photos/image/upload/w_64,d_people:generic:headshot:67:current.png,q_auto:best,f_auto/v1/people/${pitcher.pitcher_id}/headshot/67/current`}
                alt=""
                width={24}
                height={32}
                loading="lazy"
                onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
              />
              <div className="team-pitcher-usage-copy">
                <strong>{pitcher.pitcher_name}</strong>
                <span>{pitcherUsageMeta(view, basis, pitcher)}</span>
              </div>
              <strong className="team-pitcher-usage-value">{integer.format(pitcher[key])}</strong>
            </li>
          ))}
        </ol>
      ) : <p className="secondary">No qualifying pitcher workloads.</p>}
    </section>
  );
}

function TeamSeriesPanel({
  team, series, dateDomain, completeGames, pitcherUsage, view, basis, mode, contextText, open, onModeChange, onClose,
}: {
  team: Team;
  series: CumulativePoint[];
  dateDomain: DateDomain;
  completeGames: CompleteGame[];
  pitcherUsage: TeamPitcherUsage | null;
  view: View;
  basis: Basis;
  mode: SeriesMode;
  contextText: string;
  open: boolean;
  onModeChange: (mode: SeriesMode) => void;
  onClose: () => void;
}) {
  const width = 320;
  const height = 188;
  const plot = {left: 36, top: 10, width: 276, height: 140};
  const first = series[0];
  const last = series[series.length - 1];
  const valueDomain = seriesValueDomain(series, view);
  const share = view === "share" ? shareAreas(series, dateDomain, plot) : null;
  const path = share ? share.line : seriesPath(series, dateDomain, valueDomain, plot);
  const title = seriesTitle(view, basis, mode);
  const xTicks = monthAxisTicks(dateDomain);
  const yTicks = valueAxisTicks(valueDomain.min, valueDomain.max, view);
  const copyRef = useRef<HTMLDivElement>(null);
  const [badgePx, setBadgePx] = useState(64);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  useEffect(() => {
    const el = copyRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const sync = () => setBadgePx(Math.max(48, Math.round(el.getBoundingClientRect().height)));
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [title, team.team_name, contextText]);
  useEffect(() => {
    setHoverIndex(null);
  }, [team.team_id, view, basis, mode]);

  const hover = hoverIndex == null ? null : series[hoverIndex] ?? null;
  const hoverX = hover ? dateToX(hover.date, dateDomain, plot.left, plot.width) : 0;
  const hoverY = hover ? pointY(hover.value, valueDomain, plot.top, plot.height) : 0;
  const plotBottom = plot.top + plot.height;

  function handleChartMove(event: {currentTarget: SVGSVGElement; clientX: number}) {
    setHoverIndex(nearestSeriesIndexByDate(
      series,
      dateDomain,
      plot.left,
      plot.width,
      chartPointerX(event, width),
    ));
  }

  return (
    <aside
      className={`team-series-panel${open ? " is-open" : ""}`}
      aria-label={`${team.team_name} pitch timeline`}
      aria-hidden={!open}
    >
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
          <div className="team-series-chart-wrap">
            <svg
              className={`team-series-chart${share ? " share-chart" : ""}`}
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label={title}
              onMouseMove={handleChartMove}
              onMouseLeave={() => setHoverIndex(null)}
            >
              {yTicks.map((tick) => {
                const y = pointY(tick, valueDomain, plot.top, plot.height);
                return (
                  <g key={`y-${tick}`}>
                    <line
                      className="series-grid"
                      x1={plot.left}
                      x2={plot.left + plot.width}
                      y1={y}
                      y2={y}
                    />
                    <text
                      className="series-axis-label"
                      x={plot.left - 6}
                      y={y}
                      textAnchor="end"
                      dominantBaseline="middle"
                    >
                      {formatAxisValue(tick, view)}
                    </text>
                  </g>
                );
              })}
              {xTicks.map((tick) => {
                const x = dateToX(tick.date, dateDomain, plot.left, plot.width);
                return (
                  <text
                    key={`x-${tick.date}`}
                    className="series-axis-label"
                    x={x}
                    y={plotBottom + 14}
                    textAnchor="middle"
                  >
                    {tick.label}
                  </text>
                );
              })}
              <line
                className="series-axis"
                x1={plot.left}
                x2={plot.left}
                y1={plot.top}
                y2={plotBottom}
              />
              <line
                className="series-axis"
                x1={plot.left}
                x2={plot.left + plot.width}
                y1={plotBottom}
                y2={plotBottom}
              />
              {share ? (
                <>
                  <path className="series-sp-area" d={share.sp} />
                  <path className="series-rp-area" d={share.rp} />
                </>
              ) : null}
              <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
              {hover ? (
                <>
                  <line
                    className="series-hover-guide"
                    x1={hoverX}
                    x2={hoverX}
                    y1={plot.top}
                    y2={plotBottom}
                  />
                  <circle
                    className="series-hover-dot"
                    cx={hoverX}
                    cy={hoverY}
                    r={4}
                  />
                </>
              ) : null}
            </svg>
            {hover ? (
              <div
                className={`series-tooltip${hoverX < width * 0.25 ? " start" : hoverX > width * 0.75 ? " end" : ""}`}
                style={{left: `${(hoverX / width) * 100}%`}}
                role="status"
              >
                {seriesTooltipText(hover, view)}
              </div>
            ) : null}
          </div>
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
          <p className="secondary team-series-cgs">{completeGameSummary(completeGames)}</p>
          <TeamPitcherUsageList usage={pitcherUsage} view={view} basis={basis} />
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
            const rowClass = [
              seriesEnabled ? "team-row" : undefined,
              selected ? "selected" : undefined,
            ].filter(Boolean).join(" ") || undefined;
            return (
              <tr
                key={team.team_id}
                className={rowClass}
                role={seriesEnabled ? "button" : undefined}
                tabIndex={seriesEnabled ? 0 : undefined}
                aria-pressed={seriesEnabled ? selected : undefined}
                title={seriesEnabled ? undefined : "Timeline unavailable for this framing"}
                onClick={seriesEnabled ? () => onSelectTeam(team.team_id) : undefined}
                onKeyDown={seriesEnabled ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectTeam(team.team_id);
                  }
                } : undefined}
              >
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
                {showContext ? <td className="context secondary">{context(team, league, view, basis)}</td> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}


function PlayerTotalTable({
  pitchers, selectedPitcherId, onSelectPitcher,
}: {
  pitchers: PlayerTotal[];
  selectedPitcherId: number | null;
  onSelectPitcher: (pitcherId: number) => void;
}) {
  const maximum = Math.max(...pitchers.map((pitcher) => pitcher.total), 1);
  return (
    <section className="table-shell">
      <table className="player-total-table">
        <caption>Top 30 MLB pitchers ranked by total pitches thrown</caption>
        <thead>
          <tr>
            <th className="rank">Rank</th>
            <th>Pitcher</th>
            <th className="player-team-heading" aria-label="Current team">
              <span aria-hidden="true" className="player-team-heading-long">Current team</span>
              <span aria-hidden="true" className="player-team-heading-short">Team</span>
            </th>
            <th className="player-total-heading">Total pitches</th>
          </tr>
        </thead>
        <tbody>
          {pitchers.map((pitcher, index) => {
            const width = Math.max(2, pitcher.total / maximum * 100);
            return (
              <tr
                key={pitcher.pitcher_id}
                className={`player-row${selectedPitcherId === pitcher.pitcher_id ? " selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={selectedPitcherId === pitcher.pitcher_id}
                onClick={() => onSelectPitcher(pitcher.pitcher_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectPitcher(pitcher.pitcher_id);
                  }
                }}
              >
                <td className="rank">{index + 1}</td>
                <td className="team">
                  <span className="team-name">
                    <img
                      className="pitcher-portrait"
                      src={`https://img.mlbstatic.com/mlb-photos/image/upload/w_64,d_people:generic:headshot:67:current.png,q_auto:best,f_auto/v1/people/${pitcher.pitcher_id}/headshot/67/current`}
                      alt=""
                      width={24}
                      height={32}
                      loading="lazy"
                      onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
                    />
                    {pitcher.pitcher_name}
                  </span>
                </td>
                <td className="team player-team-cell" aria-label={pitcher.team_name} title={pitcher.team_name}>
                  <span className="team-name">
                    <img
                      className="team-logo player-team-logo"
                      src={`https://www.mlbstatic.com/team-logos/${pitcher.team_id}.svg`}
                      alt=""
                      width={22}
                      height={22}
                      loading="lazy"
                      onError={(event) => { event.currentTarget.classList.add("is-hidden"); }}
                    />
                    <span className="player-team-name">{pitcher.team_name}</span>
                    <span aria-hidden="true" className="player-team-abbreviation">
                      {teamAbbreviation(pitcher.team_id, pitcher.team_name)}
                    </span>
                  </span>
                </td>
                <td>
                  <div className="metric">
                    <strong>{integer.format(pitcher.total)}</strong>
                    <span className="track"><span className="fill" style={{width: `${width}%`}} /></span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function Dashboard({
  data, timeseries, playerHistory,
}: {
  data: DashboardData;
  timeseries: TeamTimeseriesData;
  playerHistory: PlayerHistoryData;
}) {
  const [screen, setScreen] = useState<"leaders" | "strain">("strain");
  const [recentTeamId, setRecentTeamId] = useState(119);
  const [view, setView] = useState<View>("total");
  const [basis, setBasis] = useState<Basis>("adjusted");
  const [sortColumn, setSortColumn] = useState<SortColumn>("metric");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [perGame, setPerGame] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [seriesMode, setSeriesMode] = useState<SeriesMode>("cumulative");
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null);
  const closingRef = useRef(false);
  const league = useMemo(() => leagueTotals(data.teams), [data.teams]);
  const dateDomain = useMemo(() => seriesDateDomain(timeseries.points), [timeseries.points]);
  const roleView = view === "sp" || view === "rp" || view === "share";
  const selectedTeam = data.teams.find((team) => team.team_id === selectedTeamId) ?? null;
  const selectedPitcherUsage = data.team_pitcher_usage.find(
    (usage) => usage.team_id === selectedTeamId,
  ) ?? null;
  const selectedPlayer = data.player_totals.find((pitcher) => pitcher.pitcher_id === selectedPlayerId) ?? null;
  const selectedPlayerHistory = playerHistory.players.find(
    (player) => player.pitcher_id === selectedPlayerId,
  ) ?? null;
  const selectedSeries = useMemo(
    () => (selectedTeamId == null || view === "players"
      ? []
      : metricSeries(timeseries.points, selectedTeamId, view, basis, seriesMode)),
    [timeseries.points, selectedTeamId, view, basis, seriesMode],
  );
  const completeGames = useMemo(
    () => (selectedTeamId == null
      ? []
      : completeGamesForTeam(timeseries.complete_games, selectedTeamId)),
    [timeseries.complete_games, selectedTeamId],
  );

  function beginClose() {
    closingRef.current = true;
    setPanelOpen(false);
  }

  useEffect(() => {
    if (selectedTeamId == null) {
      setPanelOpen(false);
      return;
    }
    closingRef.current = false;
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setPanelOpen(true));
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [selectedTeamId]);

  useEffect(() => {
    if (panelOpen || !closingRef.current || selectedTeamId == null) return;
    const reduce = typeof window !== "undefined"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(() => {
      closingRef.current = false;
      setSelectedTeamId(null);
    }, reduce ? 0 : 220);
    return () => clearTimeout(timer);
  }, [panelOpen, selectedTeamId]);

  function handleSort(column: SortColumn) {
    const next = nextSort(sortColumn, sortDirection, column);
    setSortColumn(next.column);
    setSortDirection(next.direction);
  }

  function handleView(next: View) {
    setView(next);
    if (!seriesSupported(next) && selectedTeamId != null) beginClose();
    if (next !== "players") setSelectedPlayerId(null);
  }

  function handleSelectTeam(teamId: number) {
    if (!seriesSupported(view)) return;
    if (selectedTeamId === teamId && panelOpen) {
      beginClose();
      return;
    }
    setSelectedTeamId(teamId);
  }

  function handleSelectPlayer(pitcherId: number) {
    setSelectedPlayerId((selected) => selected === pitcherId ? null : pitcherId);
  }

  const showPanel = view !== "players" && selectedTeam != null && dateDomain != null;
  const layoutWithPanel = showPanel;

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">MLB season workload</p>
        <h1>{screen === "leaders" ? "Who has thrown the most pitches?" : "What did this staff just throw?"}</h1>
        <p className="lede">{screen === "leaders"
          ? "Compare total, starter, and bullpen workloads with an auditable adjustment for openers and bulk appearances."
          : "Review the pitcher workloads from a team's most recently completed game."}</p>
      </header>
      <nav className="screen-selector" aria-label="Dashboard screen">
        <button type="button" className={screen === "strain" ? "active" : undefined} onClick={() => setScreen("strain")}>Recent strain</button>
        <button type="button" className={screen === "leaders" ? "active" : undefined} onClick={() => setScreen("leaders")}>Season leaders</button>
      </nav>
      {screen === "leaders" ? (
        <>
          {view !== "players" ? <LeagueGrid league={league} /> : null}
          <section className="controls" aria-label="Table controls">
            <div className="framing">
              {FRAMINGS.map((item) => <button key={item.view} type="button" className={view === item.view ? "active" : undefined} onClick={() => handleView(item.view)}>{item.label}</button>)}
            </div>
            {roleView && <label>Role basis<select value={basis} onChange={(event) => setBasis(event.target.value as Basis)}><option value="adjusted">Role-adjusted</option><option value="official">Official appearance</option></select></label>}
            {view !== "share" && view !== "players" && <label className="check"><input type="checkbox" checked={perGame} onChange={(event) => setPerGame(event.target.checked)} />Per game</label>}
          </section>
          {view === "players" ? (
            <div className={selectedPlayer && selectedPlayerHistory ? "table-with-panel" : undefined}>
              <PlayerTotalTable
                pitchers={data.player_totals}
                selectedPitcherId={selectedPlayerId}
                onSelectPitcher={handleSelectPlayer}
              />
              {selectedPlayer && selectedPlayerHistory ? (
                <PlayerHistoryPanel
                  pitcher={selectedPlayer}
                  history={selectedPlayerHistory}
                  onClose={() => setSelectedPlayerId(null)}
                />
              ) : null}
            </div>
          ) : (
            <div className={layoutWithPanel ? "table-with-panel" : undefined}>
            <TeamTable
              teams={data.teams}
              league={league}
              view={view}
              basis={basis}
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              perGame={perGame}
              selectedTeamId={showPanel ? selectedTeamId : null}
              seriesEnabled={seriesSupported(view)}
              showContext={!showPanel}
              onSort={handleSort}
              onSelectTeam={handleSelectTeam}
            />
            {showPanel && selectedTeam && dateDomain ? (
              <TeamSeriesPanel
                team={selectedTeam}
                series={selectedSeries}
                dateDomain={dateDomain}
                completeGames={completeGames}
                pitcherUsage={selectedPitcherUsage}
                view={view}
                basis={basis}
                mode={seriesMode}
                contextText={context(selectedTeam, league, view, basis)}
                open={panelOpen}
                onModeChange={setSeriesMode}
                onClose={beginClose}
              />
            ) : null}
            </div>
          )}
        </>
      ) : (
        <RecentStrain
          games={data.recent_games}
          nextGames={data.next_games}
          bullpenUsage={data.bullpen_usage}
          starterRest={data.starter_rest}
          selectedTeamId={recentTeamId}
          onSelectTeam={setRecentTeamId}
        />
      )}
      <footer>
        Official appearance uses MLB’s per-game starter flag. Role-adjusted classifications preserve true starters behind openers while flagging ambiguous long outings for review.
        {data.data_commit ? <> Data revision <code>{data.data_commit.slice(0, 8)}</code>.</> : null}
      </footer>
      <SnapshotPanel data={data} />
    </main>
  );
}
