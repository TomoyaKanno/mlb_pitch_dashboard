import type { Status } from "../api";
import { integer } from "../lib/format";

interface Described {
  text: string;
  detail: string;
  tone: "normal" | "warning" | "failed";
}

// Ported from the original formatStatus(): the same running / failed / idle
// states, plus the skipped-game note surfaced by the fault-tolerant refresh.
export function describe(status: Status | null, networkError: string | null): Described {
  // Request errors must never be hidden behind an older successful status.
  if (networkError) return { text: `Dashboard error: ${networkError}`, detail: "", tone: "failed" };
  if (!status) return { text: "Checking local data…", detail: "", tone: "normal" };

  if (status.running) {
    const progress = status.games_total
      ? `${status.games_processed}/${status.games_total} games`
      : status.phase;
    return {
      text: `Refreshing ${status.season}: ${progress}`,
      detail: `${integer.format(status.api_calls || 0)} API calls`,
      tone: "normal",
    };
  }

  if (status.error) {
    return {
      text: `Refresh failed: ${status.error}`,
      detail: `${integer.format(status.api_calls || 0)} API calls`,
      tone: "failed",
    };
  }

  const text = status.last_refresh_at
    ? `Last refreshed ${new Date(status.last_refresh_at).toLocaleString()}`
    : "No refresh has run yet";
  const skipped = Number(status.last_games_failed || 0);
  const skippedNote = skipped
    ? ` · ${integer.format(skipped)} games skipped (retry to backfill)`
    : "";
  const stale = Number(status.last_games_stale || 0);
  const missing = Number(status.last_games_missing || 0);
  const coverageNote = [
    stale ? `${integer.format(stale)} stale` : "",
    missing ? `${integer.format(missing)} missing` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const coverageSuffix = coverageNote ? ` · ${coverageNote}` : "";
  const detail =
    status.last_api_calls !== undefined
      ? `${integer.format(status.last_api_calls)} API calls · ${integer.format(
          status.completed_games || 0,
        )} completed games${skippedNote}${coverageSuffix}`
      : "";
  const result = status.last_refresh_result;
  const resultPrefix = result === "partial" ? "Partial refresh · " : result === "failed" ? "Failed refresh · " : "";
  const tone = result === "failed" ? "failed" : result === "partial" ? "warning" : "normal";
  return { text: `${resultPrefix}${text}`, detail, tone };
}

export function StatusStrip({
  status,
  networkError,
}: {
  status: Status | null;
  networkError: string | null;
}) {
  const { text, detail, tone } = describe(status, networkError);
  return (
    <section className={`status-strip${tone === "normal" ? "" : ` ${tone}`}`} aria-live="polite">
      <span id="status-text">{text}</span>
      <span id="status-detail">{detail}</span>
    </section>
  );
}
