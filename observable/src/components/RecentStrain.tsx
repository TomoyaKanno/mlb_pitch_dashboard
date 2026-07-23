import type {CSSProperties} from "npm:react";
import {BULLPEN_TOTAL_WINDOWS, trailingPitchTotal} from "./metrics.js";

export interface RecentPitcher {
  pitcher_id: number;
  pitcher_name: string;
  pitches: number;
  official_started: boolean;
  appearance_order: number;
  jersey_number?: string | null;
}

export interface RecentTeamGame {
  team_id: number;
  team_name: string;
  game_pk: number;
  date: string;
  game_datetime: string | null;
  away_team_id?: number | null;
  away_team_name?: string | null;
  home_team_id?: number | null;
  home_team_name?: string | null;
  pitchers: RecentPitcher[];
}

export interface ProbableRecentStart {
  date: string;
  game_pk: number;
  pitches: number;
  opponent_name: string | null;
}

export interface NextTeamGame {
  team_id: number;
  team_name: string;
  game_pk: number;
  date: string;
  game_datetime: string | null;
  opponent_id: number;
  opponent_name: string;
  is_home: boolean;
  probable_pitcher_id: number | null;
  probable_pitcher_name: string | null;
  probable_jersey_number?: string | null;
  probable_recent_starts: ProbableRecentStart[];
  probable_days_rest: number | null;
}

export interface BullpenUsagePitcher {
  pitcher_id: number;
  pitcher_name: string;
  pitches: number[];
  depth_role?: "RP" | "CP" | null;
  depth_order?: number | null;
  on_depth_chart?: boolean;
  availability?: string | null;
  status_description?: string | null;
}

export interface BullpenUsage {
  team_id: number;
  team_name: string;
  end_date: string;
  dates: string[];
  pitchers: BullpenUsagePitcher[];
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

function BullpenHeatmap({usage}: {usage: BullpenUsage | null}) {
  return (
    <section className="bullpen-usage" aria-labelledby="bullpen-usage-title">
      <div className="bullpen-usage-header">
        <div>
          <p className="eyebrow">Recent relief usage</p>
          <h2 id="bullpen-usage-title">Bullpen, last 14 days</h2>
          <p className="secondary">
            Official reliever pitch counts by day, plus available depth-chart arms who have not
            appeared yet. IL and Minors badges mark arms who worked in this window but are no
            longer active.
          </p>
        </div>
        {usage ? (
          <span className="usage-window">
            {formatFullDate(usage.dates[0])} – {formatFullDate(usage.end_date)}
          </span>
        ) : null}
      </div>
      {usage && usage.pitchers.length > 0 ? (
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
                return (
                  <tr key={pitcher.pitcher_id} className={unused ? "bullpen-unused" : undefined}>
                    <th scope="row">
                      <span className="bullpen-pitcher-label">
                        <span>{pitcher.pitcher_name}</span>
                        {pitcher.depth_role === "CP" ? (
                          <span className="roster-badge role" title="Depth-chart closer">CL</span>
                        ) : null}
                        {pitcher.availability ? (
                          <span
                            className={`roster-badge ${pitcher.availability === "IL" ? "il" : "minors"}`}
                            title={pitcher.status_description ?? pitcher.availability}
                          >
                            {pitcher.availability}
                          </span>
                        ) : null}
                      </span>
                    </th>
                    {usage.dates.map((day, index) => {
                      const pitches = pitcher.pitches[index] ?? 0;
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
    <ul className="pitcher-appearance-list" aria-label={`${teamName} pitcher workloads from its last completed game`}>
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

function daysRestLabel(daysRest: number | null): string {
  if (daysRest == null) return "No prior starts this season";
  if (daysRest === 1) return "1 day rest";
  return `${daysRest} days rest`;
}

function ProbableStarterPanel({game}: {game: NextTeamGame}) {
  const recentStarts = game.probable_recent_starts ?? [];
  const daysRest = game.probable_days_rest ?? null;
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
                <span>{start.opponent_name ? `vs ${start.opponent_name}` : "Official start"}</span>
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

function GameContext({date, gamePk}: {date: string; gamePk: number}) {
  return (
    <div className="recent-game-context">
      <span>{formatFullDate(date)}</span>
      <a href={gameDayHref(gamePk)} target="_blank" rel="noopener noreferrer">
        Open in MLB Gameday <span aria-hidden="true">↗</span>
      </a>
    </div>
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

function recentMatchup(game: RecentTeamGame): {away: MatchupTeam; home: MatchupTeam} | null {
  if (
    game.away_team_id == null
    || !game.away_team_name
    || game.home_team_id == null
    || !game.home_team_name
  ) return null;
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
  games, nextGames, bullpenUsage, selectedTeamId, onSelectTeam,
}: {
  games: RecentTeamGame[];
  nextGames: NextTeamGame[];
  bullpenUsage: BullpenUsage[];
  selectedTeamId: number;
  onSelectTeam: (teamId: number) => void;
}) {
  const selected = games.find((game) => game.team_id === selectedTeamId) ?? games[0] ?? null;
  if (!selected) {
    return (
      <p className="secondary recent-empty">
        No completed team games are available in this snapshot.
      </p>
    );
  }
  const nextGame = nextGames.find((game) => game.team_id === selected.team_id) ?? null;
  const usage = bullpenUsage.find((item) => item.team_id === selected.team_id) ?? null;
  const totalPitches = selected.pitchers.reduce((total, pitcher) => total + pitcher.pitches, 0);
  const lastMatchup = recentMatchup(selected);

  return (
    <section className="recent-strain" aria-label="Recent strain">
      <div className="recent-strain-header">
        <div>
          <p className="eyebrow">Staff workload context</p>
          <h2>{selected.team_name}</h2>
          <p className="secondary">
            Last completed-game workloads and the next scheduled opponent. Probable starters are MLB schedule designations.
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
      <div className="recent-game-grid">
        <section className="recent-game-card" aria-label="Last completed game">
          <p className="recent-card-label">Last completed game</p>
          {lastMatchup ? (
            <Matchup away={lastMatchup.away} home={lastMatchup.home} />
          ) : (
            <div className="recent-game-body">
              <TeamLogo teamId={selected.team_id} />
              <div className="recent-game-copy">
                <strong>{selected.team_name}</strong>
                <span>Full matchup will appear after the next data refresh.</span>
              </div>
            </div>
          )}
          <GameContext date={selected.date} gamePk={selected.game_pk} />
          <div className="recent-game-copy" style={{justifyItems: "center", textAlign: "center"}}>
            <strong>{integer.format(totalPitches)} pitches · {selected.pitchers.length} pitchers used</strong>
          </div>
          <PitcherAppearanceList
            teamName={selected.team_name}
            pitchers={selected.pitchers}
          />
        </section>
        <section className="recent-game-card" aria-label="Next game">
          <p className="recent-card-label">Next game</p>
          {nextGame ? (
            <>
              <Matchup {...nextMatchup(nextGame)} />
              <GameContext date={nextGame.date} gamePk={nextGame.game_pk} />
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
    </section>
  );
}
