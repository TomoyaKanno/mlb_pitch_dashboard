import { useMemo, useState } from "react";
import { Controls } from "../components/Controls";
import { LeagueGrid } from "../components/LeagueGrid";
import { RefreshPanel } from "../components/RefreshPanel";
import { StatusStrip } from "../components/StatusStrip";
import { TeamTable } from "../components/TeamTable";
import { useDashboard } from "../hooks/useDashboard";
import { leagueTotals, type Basis, type Order, type View } from "../lib/metrics";

export default function Dashboard() {
  const [season, setSeason] = useState(() => new Date().getFullYear());
  const [force, setForce] = useState(false);
  const [view, setView] = useState<View>("total");
  const [basis, setBasis] = useState<Basis>("adjusted");
  const [order, setOrder] = useState<Order>("high");
  const [perGame, setPerGame] = useState(false);

  const { status, teams, error, startRefresh } = useDashboard(season);
  const league = useMemo(() => leagueTotals(teams), [teams]);
  const refreshing = Boolean(status?.running);

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">MLB season workload</p>
          <h1>Who has thrown the most pitches?</h1>
          <p className="lede">
            Compare total, starter, and bullpen workloads with an auditable adjustment for openers
            and bulk appearances.
          </p>
        </div>
        <RefreshPanel
          season={season}
          onSeasonChange={setSeason}
          force={force}
          onForceChange={setForce}
          onRefresh={() => startRefresh(force)}
          disabled={refreshing}
        />
      </header>

      <StatusStrip status={status} networkError={error} />
      <LeagueGrid league={league} />
      <Controls
        view={view}
        onViewChange={setView}
        basis={basis}
        onBasisChange={setBasis}
        order={order}
        onOrderChange={setOrder}
        perGame={perGame}
        onPerGameChange={setPerGame}
      />
      <TeamTable teams={teams} league={league} view={view} basis={basis} order={order} perGame={perGame} />

      <footer>
        Official appearance uses MLB’s per-game starter flag. Role-adjusted classifications and
        ambiguous long outings are available from <code>/api/audit</code>.
      </footer>
    </main>
  );
}
