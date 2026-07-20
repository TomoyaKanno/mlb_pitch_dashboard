import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Status } from "../api";
import { StatusStrip } from "./StatusStrip";

const status: Status = {
  running: false,
  phase: "partial",
  season: 2026,
  games_total: 10,
  games_processed: 9,
  games_failed: 1,
  api_calls: 12,
  error: null,
  last_refresh_at: "2026-07-20T12:00:00Z",
  last_refresh_result: "partial",
  last_api_calls: 12,
  completed_games: 100,
  last_games_failed: 1,
  last_games_stale: 1,
  last_games_missing: 0,
};

describe("StatusStrip", () => {
  it("does not hide a new request error behind an older status", () => {
    render(<StatusStrip status={status} networkError="Request failed (500)" />);

    expect(screen.getByText("Dashboard error: Request failed (500)")).toBeInTheDocument();
  });

  it("reports partial refresh coverage", () => {
    render(<StatusStrip status={status} networkError={null} />);

    expect(screen.getByText(/Partial refresh/)).toBeInTheDocument();
    expect(screen.getByText(/1 stale/)).toBeInTheDocument();
  });
});
