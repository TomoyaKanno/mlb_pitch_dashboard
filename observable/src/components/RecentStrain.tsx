import type {CSSProperties} from "npm:react";

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
  game_datetime: string | null;
  away_team_id?: number | null;
  away_team_name?: string | null;
  home_team_id?: number | null;
  home_team_name?: string | null;
  pitchers: RecentPitcher[];
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
}

export interface BullpenUsagePitcher {
  pitcher_id: number;
  pitcher_name: string;
  pitches: number[];
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
            Each cell is a pitch count; blank cells are days without a relief appearance.
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
                <th scope="col">Pitcher</th>
                {usage.dates.map((day) => (
                  <th key={day} className="heat-date" scope="col" title={formatFullDate(day)}>
                    {formatShortDate(day)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usage.pitchers.map((pitcher) => (
                <tr key={pitcher.pitcher_id}>
                  <th scope="row">{pitcher.pitcher_name}</th>
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
                </tr>
              ))}
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
          <div className="recent-game-copy" style={{justifyItems: "center", textAlign: "center"}}>
            <strong>{integer.format(totalPitches)} pitches · {selected.pitchers.length} pitchers used</strong>
            <span>{formatFullDate(selected.date)} · game {selected.game_pk}</span>
          </div>
          <div className="recent-card-table">
            <table>
              <caption>{selected.team_name} pitcher workloads from its last completed game</caption>
              <thead>
                <tr>
                  <th>Pitcher</th>
                  <th className="recent-role">Role</th>
                  <th className="recent-pitches">Pitches</th>
                </tr>
              </thead>
              <tbody>
                {selected.pitchers.map((pitcher) => (
                  <tr key={pitcher.pitcher_id}>
                    <td>{pitcher.pitcher_name}</td>
                    <td className="recent-role">{pitcher.official_started ? "SP" : "RP"}</td>
                    <td className="recent-pitches">{integer.format(pitcher.pitches)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="recent-game-card" style={{alignSelf: "start"}} aria-label="Next game">
          <p className="recent-card-label">Next game</p>
          {nextGame ? (
            <>
              <Matchup {...nextMatchup(nextGame)} />
              <div className="recent-game-copy" style={{justifyItems: "center", textAlign: "center"}}>
                <strong>{formatFullDate(nextGame.date)}</strong>
                <span>game {nextGame.game_pk}</span>
                <span className="probable-starter">
                  {selected.team_name} probable starter: {nextGame.probable_pitcher_name ?? "Not announced"}
                </span>
              </div>
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
