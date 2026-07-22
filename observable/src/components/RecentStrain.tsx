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

function TeamLogo({teamId}: {teamId: number}) {
  return (
    <img
      className="recent-team-logo"
      src={`https://www.mlbstatic.com/team-logos/${teamId}.svg`}
      alt=""
      width={54}
      height={54}
      onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
    />
  );
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
          <div className="recent-game-body">
            <TeamLogo teamId={selected.team_id} />
            <div className="recent-game-copy">
              <strong>{integer.format(totalPitches)} pitches</strong>
              <span>{selected.pitchers.length} pitchers used · {formatFullDate(selected.date)}</span>
            </div>
          </div>
        </section>
        <section className="recent-game-card" aria-label="Next game">
          <p className="recent-card-label">Next game</p>
          {nextGame ? (
            <div className="recent-game-body">
              <TeamLogo teamId={nextGame.opponent_id} />
              <div className="recent-game-copy">
                <strong>{nextGame.is_home ? `vs. ${nextGame.opponent_name}` : `at ${nextGame.opponent_name}`}</strong>
                <span>{formatFullDate(nextGame.date)} · game {nextGame.game_pk}</span>
                <span className="probable-starter">
                  Probable starter: {nextGame.probable_pitcher_name ?? "Not announced"}
                </span>
              </div>
            </div>
          ) : (
            <div className="recent-game-copy">
              <strong>No upcoming game</strong>
              <span>Next-game schedule data will appear after a refresh.</span>
            </div>
          )}
        </section>
      </div>
      <div className="table-shell recent-table">
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
      <BullpenHeatmap usage={usage} />
    </section>
  );
}
