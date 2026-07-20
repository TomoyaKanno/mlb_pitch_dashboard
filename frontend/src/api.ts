// Types and thin fetch wrappers for the FastAPI backend. Keeping the network
// surface in one module means new pages get typed data by importing from here
// rather than hand-rolling fetch calls.

export interface Team {
  team_id: number;
  team_name: string;
  games: number;
  total: number;
  official_sp: number;
  official_rp: number;
  adjusted_sp: number;
  adjusted_rp: number;
  bulk_to_sp: number;
  opener_to_rp: number;
  review_count: number;
}

export interface Status {
  running: boolean;
  phase: string;
  season: number;
  games_total: number;
  games_processed: number;
  games_failed: number;
  api_calls: number;
  error: string | null;
  last_refresh_at?: string;
  last_refresh_season?: number;
  last_api_calls?: number;
  last_games_fetched?: number;
  last_games_failed?: number;
  completed_games?: number;
}

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

export function fetchStatus(): Promise<Status> {
  return getJSON<Status>("/api/status");
}

export async function fetchTeams(season: number): Promise<Team[]> {
  const payload = await getJSON<{ season: number; teams: Team[] }>(
    `/api/teams?season=${encodeURIComponent(season)}`,
  );
  return payload.teams;
}

export async function postRefresh(season: number, force: boolean): Promise<void> {
  const response = await fetch("/api/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ season, force }),
  });
  if (!response.ok) {
    let detail = "Refresh request failed";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // non-JSON error body; keep the default message
    }
    throw new Error(detail);
  }
}
