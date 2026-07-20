import type { LeagueTotals } from "../lib/metrics";
import { decimal, integer } from "../lib/format";

export function LeagueGrid({ league }: { league: LeagueTotals }) {
  const total = league.total
    ? integer.format(league.total)
    : "—";
  const spShare = league.total
    ? `${decimal.format((league.adjusted_sp / league.total) * 100)}%`
    : "—";
  const reclassified = integer.format(league.bulk_to_sp + league.opener_to_rp);
  const review = integer.format(league.review_count);

  return (
    <section className="league-grid" aria-label="League summary">
      <div>
        <strong id="league-total">{total}</strong>
        <span>Total pitches</span>
      </div>
      <div>
        <strong id="league-sp-share">{spShare}</strong>
        <span>Adjusted SP share</span>
      </div>
      <div>
        <strong id="league-reclassified">{reclassified}</strong>
        <span>Reclassified pitches</span>
      </div>
      <div>
        <strong id="league-review">{review}</strong>
        <span>Appearances to review</span>
      </div>
    </section>
  );
}
