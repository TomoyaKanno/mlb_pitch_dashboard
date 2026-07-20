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
  const [requestingRefresh, setRequestingRefresh] = useState(false);

  const timer = useRef<number | undefined>(undefined);
  const pollGeneration = useRef(0);
  const teamRequest = useRef(0);
  const seasonEffectReady = useRef(false);
  const seasonRef = useRef(season);
  seasonRef.current = season;

  const loadTeams = useCallback(async () => {
    const requestId = ++teamRequest.current;
    try {
      const nextTeams = await fetchTeams(seasonRef.current);
      if (requestId !== teamRequest.current) return;
      setTeams(nextTeams);
      setError(null);
    } catch (err) {
      if (requestId !== teamRequest.current) return;
      setError((err as Error).message);
    }
  }, []);

  const poll = useCallback(async (generation: number): Promise<void> => {
    try {
      const next = await fetchStatus();
      if (generation !== pollGeneration.current) return;
      setStatus(next);
      setError(null);
      setRequestingRefresh(false);
      if (next.running) {
        if (timer.current) window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => void poll(generation), 1200);
      } else {
        await loadTeams();
      }
    } catch (err) {
      if (generation !== pollGeneration.current) return;
      setError((err as Error).message);
      // A transient status failure must not strand a running refresh. Keep
      // retrying at a slower cadence until the backend is reachable again.
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void poll(generation), 2500);
    }
  }, [loadTeams]);

  const startRefresh = useCallback(
    async (force: boolean) => {
      setRequestingRefresh(true);
      setError(null);
      try {
        await postRefresh(seasonRef.current, force);
        await poll(pollGeneration.current);
      } catch (err) {
        setError((err as Error).message);
        setRequestingRefresh(false);
      }
    },
    [poll],
  );

  // Initial status check on mount; clear any pending poll on unmount.
  useEffect(() => {
    const generation = ++pollGeneration.current;
    void poll(generation);
    return () => {
      pollGeneration.current += 1;
      teamRequest.current += 1;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [poll]);

  // Reload the table when the season changes.
  useEffect(() => {
    if (!seasonEffectReady.current) {
      seasonEffectReady.current = true;
      return;
    }
    void loadTeams();
  }, [season, loadTeams]);

  return { status, teams, error, requestingRefresh, startRefresh };
}
