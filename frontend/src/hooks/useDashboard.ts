import { useCallback, useEffect, useRef, useState } from "react";
import { fetchStatus, fetchTeams, postRefresh, type Status, type Team } from "../api";

// Owns the refresh lifecycle: it polls /api/status while a refresh runs (the
// same 1.2s cadence as the original app), then reloads team totals when the
// refresh settles. Season is read through a ref so the recursive poll always
// uses the latest value without being torn down and recreated mid-flight.
export function useDashboard(season: number) {
  const [status, setStatus] = useState<Status | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [error, setError] = useState<string | null>(null);

  const timer = useRef<number | undefined>(undefined);
  const seasonRef = useRef(season);
  seasonRef.current = season;

  const loadTeams = useCallback(async () => {
    try {
      setTeams(await fetchTeams(seasonRef.current));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const next = await fetchStatus();
      setStatus(next);
      setError(null);
      if (next.running) {
        timer.current = window.setTimeout(poll, 1200);
      } else {
        await loadTeams();
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [loadTeams]);

  const startRefresh = useCallback(
    async (force: boolean) => {
      try {
        await postRefresh(seasonRef.current, force);
        await poll();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [poll],
  );

  // Initial status check on mount; clear any pending poll on unmount.
  useEffect(() => {
    void poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [poll]);

  // Reload the table when the season changes.
  useEffect(() => {
    void loadTeams();
  }, [season, loadTeams]);

  return { status, teams, error, startRefresh };
}
