interface RefreshPanelProps {
  season: number;
  onSeasonChange: (season: number) => void;
  force: boolean;
  onForceChange: (force: boolean) => void;
  onRefresh: () => void;
  disabled: boolean;
}

export function RefreshPanel({
  season,
  onSeasonChange,
  force,
  onForceChange,
  onRefresh,
  disabled,
}: RefreshPanelProps) {
  return (
    <div className="refresh-panel">
      <label>
        Season
        <input
          id="season"
          type="number"
          min={2000}
          max={2100}
          value={season}
          onChange={(event) => onSeasonChange(Number(event.target.value))}
        />
      </label>
      <label className="check">
        <input
          id="force"
          type="checkbox"
          checked={force}
          onChange={(event) => onForceChange(event.target.checked)}
        />
        Force rebuild
      </label>
      <button id="refresh" type="button" onClick={onRefresh} disabled={disabled}>
        Refresh from MLB
      </button>
    </div>
  );
}
