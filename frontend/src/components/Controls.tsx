import type { Basis, Order, View } from "../lib/metrics";

const FRAMINGS: { view: View; label: string }[] = [
  { view: "total", label: "Total" },
  { view: "sp", label: "SP workload" },
  { view: "rp", label: "RP workload" },
  { view: "share", label: "Bullpen share" },
  { view: "adjustment", label: "Role adjustment" },
];

interface ControlsProps {
  view: View;
  onViewChange: (view: View) => void;
  basis: Basis;
  onBasisChange: (basis: Basis) => void;
  order: Order;
  onOrderChange: (order: Order) => void;
  perGame: boolean;
  onPerGameChange: (perGame: boolean) => void;
}

export function Controls({
  view,
  onViewChange,
  basis,
  onBasisChange,
  order,
  onOrderChange,
  perGame,
  onPerGameChange,
}: ControlsProps) {
  const roleView = view === "sp" || view === "rp" || view === "share";
  const showPerGame = view !== "share";

  return (
    <section className="controls" aria-label="Table controls">
      <div className="framing" id="framing">
        {FRAMINGS.map((framing) => (
          <button
            key={framing.view}
            type="button"
            className={view === framing.view ? "active" : undefined}
            onClick={() => onViewChange(framing.view)}
          >
            {framing.label}
          </button>
        ))}
      </div>

      {roleView && (
        <label id="basis-wrap">
          Role basis
          <select value={basis} onChange={(event) => onBasisChange(event.target.value as Basis)}>
            <option value="adjusted">Role-adjusted</option>
            <option value="official">Official appearance</option>
          </select>
        </label>
      )}

      <label>
        Order
        <select value={order} onChange={(event) => onOrderChange(event.target.value as Order)}>
          <option value="high">Highest first</option>
          <option value="low">Lowest first</option>
          <option value="alpha">Team A–Z</option>
        </select>
      </label>

      {showPerGame && (
        <label className="check" id="per-game-wrap">
          <input
            type="checkbox"
            checked={perGame}
            onChange={(event) => onPerGameChange(event.target.checked)}
          />
          Per game
        </label>
      )}
    </section>
  );
}
