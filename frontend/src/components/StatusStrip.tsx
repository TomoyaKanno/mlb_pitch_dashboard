import type { Status } from "../api";
import { integer } from "../lib/format";

interface Described {
  text: string;
  detail: string;
  failed: boolean;
}

// Ported from the original formatStatus(): the same running / failed / idle
// states, plus the skipped-game note surfaced by the fault-tolerant refresh.
function describe(status: Status | null, networkError: string | null): Described {
  if (networkError && !status) return { text: networkError, detail: "", failed: true };
  if (!status) return { text: "Checking local data…", detail: "", failed: false };

  if (status.running) {
    const progress = status.games_total
      ? `${status.games_processed}/${status.games_total} games`
      : status.phase;
    return {
      text: `Refreshing ${status.season}: ${progress}`,
      detail: `${integer.format(status.api_calls || 0)} API calls`,
      failed: false,
    };
  }

  if (status.error) {
    return {
      text: `Refresh failed: ${status.error}`,
      detail: `${integer.format(status.api_calls || 0)} API calls`,
      failed: true,
    };
  }

  const text = status.last_refresh_at
    ? `Last refreshed ${new Date(status.last_refresh_at).toLocaleString()}`
    : "No refresh has run yet";
  const skipped = Number(status.last_games_failed || 0);
  const skippedNote = skipped
    ? ` · ${integer.format(skipped)} games skipped (retry to backfill)`
    : "";
  const detail =
    status.last_api_calls !== undefined
      ? `${integer.format(status.last_api_calls)} API calls · ${integer.format(
          status.completed_games || 0,
        )} completed games${skippedNote}`
      : "";
  return { text, detail, failed: false };
}

export function StatusStrip({
  status,
  networkError,
}: {
  status: Status | null;
  networkError: string | null;
}) {
  const { text, detail, failed } = describe(status, networkError);
  return (
    <section className={`status-strip${failed ? " failed" : ""}`} aria-live="polite">
      <span id="status-text">{text}</span>
      <span id="status-detail">{detail}</span>
    </section>
  );
}
