import {useEffect, useState, type CSSProperties} from "npm:react";
import {
  BULLPEN_TOTAL_WINDOWS, daysRestLabel, nextGameTimeStatus, trailingPitchTotal,
  type NextGameTimeStatus,
} from "./metrics.js";

export interface RecentPitcher {
  pitcher_id: number;
  pitcher_name: string;
  pitches: number;
  official_started: boolean;
  appearance_order: number;
}

export interface RecentTeamGame {
  team_id: number;
  team_name: string;
  game_pk: number;
  date: string;
  game_datetime: string;
  away_team_id: number;
  away_team_name: string;
  home_team_id: number;
  home_team_name: string;
  pitchers: RecentPitcher[];
}

export interface ProbableRecentStart {
  date: string;
  game_pk: number;
  pitches: number;
  opponent_name: string;
}

export interface NextTeamGame {
  team_id: number;
  team_name: string;
  game_pk: number;
  date: string;
  game_datetime: string;
  opponent_id: number;
  opponent_name: string;
  is_home: boolean;
  probable_pitcher_id: number | null;
  probable_pitcher_name: string | null;
  probable_recent_starts: ProbableRecentStart[];
  probable_days_rest: number | null;
  is_rest_day_today: boolean;
  schedule_date: string;
}

export interface BullpenUsagePitcher {
  pitcher_id: number;
  pitcher_name: string;
  pitches: number[];
  depth_role: "RP" | "CP" | null;
  depth_order: number | null;
  on_depth_chart: boolean;
  availability: string | null;
  status_description: string | null;
}

export interface BullpenUsage {
  team_id: number;
  team_name: string;
  end_date: string;
  dates: string[];
  pitchers: BullpenUsagePitcher[];
}

export interface StarterRestPitcher {
  pitcher_id: number;
  pitcher_name: string;
  depth_role: "SP";
  depth_order: number;
  status_code: "A";
  last_start_date: string | null;
  last_start_pitches: number | null;
  days_rest: number | null;
}

export interface StarterRest {
  team_id: number;
  team_name: string;
  as_of_date: string;
  pitchers: StarterRestPitcher[];
}

interface MatchupTeam {
  teamId: number;
  teamName: string;
  isFocus: boolean;
}

const integer = new Intl.NumberFormat("en-US");
const fullDate = new Intl.DateTimeFormat("en-US", {
  month: "long",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});
const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const HEATMAP_SATURATION_PITCHES = 30;

function parseDate(value: string): Date {
  return new Date(value + "T00:00:00Z");
}

function formatFullDate(value: string): string {
  return fullDate.format(parseDate(value));
}

function formatShortDate(value: string): string {
  return shortDate.format(parseDate(value));
}

function heatCellStyle(pitches: number): CSSProperties | undefined {
  if (!pitches) return undefined;
  const ratio = Math.min(pitches, HEATMAP_SATURATION_PITCHES) / HEATMAP_SATURATION_PITCHES;
  const accentShare = 20 + Math.round(ratio * 70);
  return {background: `color-mix(in srgb, var(--accent) ${accentShare}%, var(--surface))`};
}

function BullpenHeatmap({usage}: {usage: BullpenUsage}) {
  return (
    <section className="bullpen-usage" aria-labelledby="bullpen-usage-title">
      <div className="bullpen-usage-header">
        <div>
          <p className="eyebrow">Recent relief usage</p>
          <h2 id="bullpen-usage-title">Bullpen, last 14 days</h2>
          <p className="secondary">
            Official reliever pitch counts by day, plus available depth-chart arms who have not
            appeared yet. Non-active rows retain their recent usage but are muted because those
            pitchers are no longer available.
          </p>
        </div>
        <span className="usage-window">
          {formatFullDate(usage.dates[0])} – {formatFullDate(usage.end_date)}
        </span>
      </div>
      {usage.pitchers.length > 0 ? (
        <div className="heatmap-scroll">
          <table className="bullpen-heatmap">
            <thead>
              <tr>
                <th scope="col" rowSpan={2}>Pitcher</th>
                {usage.dates.map((day) => (
                  <th key={day} className="heat-date" scope="col" rowSpan={2} title={formatFullDate(day)}>
                    {formatShortDate(day)}
                  </th>
                ))}
                <th className="heat-total-group" scope="colgroup" colSpan={BULLPEN_TOTAL_WINDOWS.length}>
                  Pitch totals
                </th>
              </tr>
              <tr>
                {BULLPEN_TOTAL_WINDOWS.map((days, index) => (
                  <th
                    key={days}
                    className={"heat-total-heading" + (index === 0 ? " heat-total-start" : "")}
                    scope="col"
                  >
                    {days}D
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usage.pitchers.map((pitcher) => {
                const unused = pitcher.on_depth_chart && pitcher.pitches.every((value) => value === 0);
                const unavailable = pitcher.availability !== null;
                const rowClass = [
                  unused ? "bullpen-unused" : undefined,
                  unavailable ? "bullpen-unavailable" : undefined,
                ].filter(Boolean).join(" ") || undefined;
                return (
                  <tr key={pitcher.pitcher_id} className={rowClass}>
                    <th scope="row">
                      <span className="bullpen-pitcher-label">
                        <span>{pitcher.pitcher_name}</span>
                        {pitcher.depth_role === "CP" ? (
                          <span className="roster-badge role" title="Depth-chart closer">CL</span>
                        ) : null}
                        {pitcher.availability ? (
                          <span
                            className={`roster-badge ${pitcher.availability === "IL" ? "il" : "unavailable"}`}
                            title={pitcher.status_description ?? pitcher.availability}
                          >
                            {pitcher.availability}
                          </span>
                        ) : null}
                      </span>
                    </th>
                    {usage.dates.map((day, index) => {
                      const pitches = pitcher.pitches[index];
                      const description = pitches ? `${pitches} pitches` : "no pitches";
                      const label = `${pitcher.pitcher_name}: ${description} on ${formatFullDate(day)}`;
                      return (
                        <td
                          key={day}
                          className={`heat-cell${pitches ? " used" : ""}`}
                          style={heatCellStyle(pitches)}
                          title={label}
                          aria-label={label}
                        >
                          {pitches || ""}
                        </td>
                      );
                    })}
                    {BULLPEN_TOTAL_WINDOWS.map((days, index) => {
                      const pitches = trailingPitchTotal(pitcher.pitches, days);
                      const label = pitcher.pitcher_name + ": " + pitches
                        + " official relief pitches in the last " + days
                        + " calendar days ending " + formatFullDate(usage.end_date);
                      return (
                        <td
                          key={days}
                          className={"heat-total-cell" + (index === 0 ? " heat-total-start" : "")}
                          title={label}
                          aria-label={label}
                        >
                          {pitches}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="secondary">No relief appearances are available in this window.</p>
      )}
    </section>
  );
}

function TeamLogo({teamId, size = 54}: {teamId: number; size?: number}) {
  return (
    <img
      className="recent-team-logo"
      src={`https://www.mlbstatic.com/team-logos/${teamId}.svg`}
      alt=""
      width={size}
      height={size}
      onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
    />
  );
}

/** MLB public CDN photo headshot; Cloudinary default covers missing photos. */
function PitcherPortrait({
  pitcherId,
  width = 32,
  height = 42,
}: {
  pitcherId: number;
  width?: number;
  height?: number;
}) {
  return (
    <img
      className="pitcher-portrait"
      src={`https://img.mlbstatic.com/mlb-photos/image/upload/w_${Math.max(width, height) * 2},d_people:generic:headshot:67:current.png,q_auto:best,f_auto/v1/people/${pitcherId}/headshot/67/current`}
      alt=""
      width={width}
      height={height}
      loading="lazy"
      onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
    />
  );
}

function splitPitcherName(fullName: string): {first: string; last: string} {
  const trimmed = fullName.trim();
  const index = trimmed.lastIndexOf(" ");
  if (index <= 0) return {first: "", last: trimmed};
  return {first: trimmed.slice(0, index), last: trimmed.slice(index + 1)};
}

function PitcherNameStack({
  name,
  meta,
}: {
  name: string;
  meta?: string;
}) {
  const {first, last} = splitPitcherName(name);
  return (
    <div className="pitcher-name-stack">
      <div className="pitcher-name-lines">
        {first ? <span className="pitcher-first">{first}</span> : null}
        <strong className="pitcher-last">{last}</strong>
        {meta ? <span className="pitcher-meta">{meta}</span> : null}
      </div>
    </div>
  );
}

function PitcherAppearanceList({
  teamName,
  pitchers,
}: {
  teamName: string;
  pitchers: RecentPitcher[];
}) {
  return (
    <ul className="pitcher-appearance-list" aria-label={`${teamName} pitcher workloads from its latest available completed game`}>
      {pitchers.map((pitcher) => (
        <li key={pitcher.pitcher_id} className="pitcher-appearance-row">
          <PitcherPortrait pitcherId={pitcher.pitcher_id} />
          <PitcherNameStack
            name={pitcher.pitcher_name}
            meta={pitcher.official_started ? "SP" : "RP"}
          />
          <span className="pitcher-appearance-pitches">{integer.format(pitcher.pitches)}</span>
        </li>
      ))}
    </ul>
  );
}

function StarterRestPanel({rest}: {rest: StarterRest}) {
  return (
    <section className="starter-rest" aria-labelledby="starter-rest-title">
      <div className="starter-rest-header">
        <div>
          <p className="eyebrow">Rotation context</p>
          <h2 id="starter-rest-title">Starter rest</h2>
          <p className="secondary">
            Active MLB depth-chart starters in published order. Rest counts official
            starts only and excludes both the start date and the as-of date.
          </p>
        </div>
        <span className="usage-window">Entering {formatFullDate(rest.as_of_date)}</span>
      </div>
      {rest.pitchers.length > 0 ? (
        <ul
          className="starter-rest-list"
          aria-label={`${rest.team_name} active starter rest entering ${formatFullDate(rest.as_of_date)}`}
        >
          {rest.pitchers.map((pitcher) => {
            const lastStart = pitcher.last_start_date
              ? `Last start ${formatShortDate(pitcher.last_start_date)}`
                + (pitcher.last_start_pitches == null
                  ? ""
                  : ` · ${integer.format(pitcher.last_start_pitches)} pitches`)
              : "No official start in this season snapshot";
            return (
              <li key={pitcher.pitcher_id} className="starter-rest-row">
                <PitcherPortrait pitcherId={pitcher.pitcher_id} width={48} height={64} />
                <PitcherNameStack name={pitcher.pitcher_name} meta={lastStart} />
                <span className="starter-rest-value">
                  {daysRestLabel(pitcher.days_rest)}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="secondary starter-rest-empty">
          No active depth-chart starters are available in this snapshot.
        </p>
      )}
    </section>
  );
}

function ProbableStarterPanel({game}: {game: NextTeamGame}) {
  const recentStarts = game.probable_recent_starts;
  const daysRest = game.probable_days_rest;
  if (game.probable_pitcher_id == null || !game.probable_pitcher_name) {
    return (
      <div className="recent-game-copy" style={{justifyItems: "center", textAlign: "center"}}>
        <span className="probable-starter">{game.team_name} probable starter: Not announced</span>
      </div>
    );
  }

  return (
    <div className="probable-starter-panel">
      <div className="probable-starter-identity">
        <PitcherPortrait pitcherId={game.probable_pitcher_id} width={72} height={96} />
        <div className="probable-starter-copy">
          <p className="recent-card-label">Probable starter</p>
          <PitcherNameStack
            name={game.probable_pitcher_name}
            meta={daysRestLabel(daysRest)}
          />

        </div>
      </div>
      {recentStarts.length > 0 ? (
        <ul
          className="probable-start-history"
          aria-label={`${game.probable_pitcher_name} last ${recentStarts.length} official starts`}
        >
          {recentStarts.map((start) => (
            <li key={start.game_pk} className="probable-start-row">
              <div className="probable-start-copy">
                <strong>{formatShortDate(start.date)}</strong>
                <span>vs {start.opponent_name}</span>
              </div>
              <span className="pitcher-appearance-pitches">{integer.format(start.pitches)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="secondary probable-start-empty">No official starts in this season snapshot yet.</p>
      )}
    </div>
  );
}

function gameDayHref(gamePk: number): string {
  return "https://www.mlb.com/gameday/" + gamePk;
}

function boxScoreHref(gamePk: number): string {
  return gameDayHref(gamePk) + "/final/box";
}

const CLOCK_REFRESH_MS = 60_000;

function useCurrentTime(): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), CLOCK_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);
  return nowMs;
}

function NextGameStatusBadge({status}: {status: Exclude<NextGameTimeStatus, null>}) {
  const label = status === "live" ? "Likely live" : "Likely over";
  return (
    <span className={`next-game-status next-game-status-${status}`} role="status">
      <span className="next-game-status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

function easternCalendarDate(): string {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(new Date())
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  ) as Record<string, string>;
  return values.year + "-" + values.month + "-" + values.day;
}

function GameContext({
  date,
  gamePk,
  destination,
}: {
  date: string;
  gamePk: number;
  destination: "box-score" | "gameday";
}) {
  const isBoxScore = destination === "box-score";
  return (
    <div className="recent-game-context">
      <span>{formatFullDate(date)}</span>
      <a
        className="game-action-button"
        href={isBoxScore ? boxScoreHref(gamePk) : gameDayHref(gamePk)}
        target="_blank"
        rel="noopener noreferrer"
      >
        {isBoxScore ? "Box score" : "MLB Gameday"} <span aria-hidden="true">↗</span>
      </a>
    </div>
  );
}

function RestDayPanel({game}: {game: NextTeamGame | null}) {
  if (
    game == null
    || !game.is_rest_day_today
    || game.schedule_date !== easternCalendarDate()
  ) return null;

  const nextMatchup = game.is_home ? "vs " + game.opponent_name : "at " + game.opponent_name;
  return (
    <section className="rest-day-panel" role="status" aria-label="Rest day">
      <div>
        <p className="rest-day-label">Rest day</p>
        <h3>No game scheduled for {game.team_name} today.</h3>
      </div>
      <p>Next game: <strong>{nextMatchup}</strong> · {formatShortDate(game.date)}</p>
    </section>
  );
}

function Matchup({away, home}: {away: MatchupTeam; home: MatchupTeam}) {
  const team = (item: MatchupTeam) => (
    <div
      style={{display: "grid", justifyItems: "center", gap: "5px", minWidth: 0}}
      title={item.isFocus ? `${item.teamName}, selected team` : item.teamName}
    >
      <TeamLogo teamId={item.teamId} size={50} />
      <strong
        style={{
          color: item.isFocus ? "var(--accent)" : "var(--text)",
          fontSize: ".85rem",
          lineHeight: 1.2,
          textAlign: "center",
        }}
      >
        {item.teamName}
      </strong>
    </div>
  );

  return (
    <div
      aria-label={`${away.teamName} at ${home.teamName}`}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) auto minmax(0, 1fr)",
        alignItems: "center",
        gap: "12px",
        padding: "4px 0",
      }}
    >
      {team(away)}
      <span
        aria-hidden="true"
        style={{color: "var(--muted)", fontSize: ".72rem", fontWeight: 700, textTransform: "uppercase"}}
      >
        at
      </span>
      {team(home)}
    </div>
  );
}

function recentMatchup(game: RecentTeamGame): {away: MatchupTeam; home: MatchupTeam} {
  return {
    away: {
      teamId: game.away_team_id,
      teamName: game.away_team_name,
      isFocus: game.away_team_id === game.team_id,
    },
    home: {
      teamId: game.home_team_id,
      teamName: game.home_team_name,
      isFocus: game.home_team_id === game.team_id,
    },
  };
}

function nextMatchup(game: NextTeamGame): {away: MatchupTeam; home: MatchupTeam} {
  const focus = {teamId: game.team_id, teamName: game.team_name, isFocus: true};
  const opponent = {teamId: game.opponent_id, teamName: game.opponent_name, isFocus: false};
  return game.is_home ? {away: opponent, home: focus} : {away: focus, home: opponent};
}

export function RecentStrain({
  games, nextGames, bullpenUsage, starterRest, selectedTeamId, onSelectTeam,
}: {
  games: RecentTeamGame[];
  nextGames: NextTeamGame[];
  bullpenUsage: BullpenUsage[];
  starterRest: StarterRest[];
  selectedTeamId: number;
  onSelectTeam: (teamId: number) => void;
}) {
  const nowMs = useCurrentTime();
  const selected = games.find((game) => game.team_id === selectedTeamId) ?? games[0] ?? null;
  if (!selected) {
    return (
      <p className="secondary recent-empty">
        No completed team games are available in this snapshot.
      </p>
    );
  }
  const nextGame = nextGames.find((game) => game.team_id === selected.team_id) ?? null;
  const nextGameStatus = nextGameTimeStatus(nextGame?.game_datetime ?? null, nowMs);
  const usage = bullpenUsage.find((item) => item.team_id === selected.team_id)!;
  const rest = starterRest.find((item) => item.team_id === selected.team_id)!;
  const totalPitches = selected.pitchers.reduce((total, pitcher) => total + pitcher.pitches, 0);
  const lastMatchup = recentMatchup(selected);

  return (
    <section className="recent-strain" aria-label="Recent strain">
      <div className="recent-strain-header">
        <div>
          <p className="eyebrow">Staff workload context</p>
          <h2>{selected.team_name}</h2>
          <p className="secondary">
            Latest available completed-game workloads and the next scheduled opponent. Probable starters are MLB schedule designations.
          </p>
        </div>
        <label>
          Team
          <select
            value={selected.team_id}
            onChange={(event) => onSelectTeam(Number(event.target.value))}
          >
            {games.map((game) => (
              <option key={game.team_id} value={game.team_id}>{game.team_name}</option>
            ))}
          </select>
        </label>
      </div>
      <RestDayPanel game={nextGame} />
      <div className="recent-game-grid">
        <section className="recent-game-card" aria-label="Latest available completed game">
          <p className="recent-card-label">Latest available completed game</p>
          <Matchup away={lastMatchup.away} home={lastMatchup.home} />
          <GameContext date={selected.date} gamePk={selected.game_pk} destination="box-score" />
          <div className="recent-game-copy" style={{justifyItems: "center", textAlign: "center"}}>
            <strong>{integer.format(totalPitches)} pitches · {selected.pitchers.length} pitchers used</strong>
          </div>
          <PitcherAppearanceList
            teamName={selected.team_name}
            pitchers={selected.pitchers}
          />
        </section>
        <section className="recent-game-card" aria-label="Next game">
          <div className="next-game-card-heading">
            <p className="recent-card-label">Next game</p>
            {nextGameStatus ? <NextGameStatusBadge status={nextGameStatus} /> : null}
          </div>
          {nextGame ? (
            <>
              <Matchup {...nextMatchup(nextGame)} />
              <GameContext date={nextGame.date} gamePk={nextGame.game_pk} destination="gameday" />
              <ProbableStarterPanel game={nextGame} />
            </>
          ) : (
            <div className="recent-game-copy">
              <strong>No upcoming game</strong>
              <span>Next-game schedule data will appear after a refresh.</span>
            </div>
          )}
        </section>
      </div>
      <BullpenHeatmap usage={usage} />
      <StarterRestPanel rest={rest} />
    </section>
  );
}
