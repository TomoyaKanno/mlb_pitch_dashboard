import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchStatus, fetchTeams, postRefresh, type Status } from "../api";
import { useDashboard } from "./useDashboard";

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return {
    ...original,
    fetchStatus: vi.fn(),
    fetchTeams: vi.fn(),
    postRefresh: vi.fn(),
  };
});

const idleStatus: Status = {
  running: false,
  phase: "complete",
  season: 2026,
  games_total: 0,
  games_processed: 0,
  games_failed: 0,
  api_calls: 0,
  error: null,
};

describe("useDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTeams).mockResolvedValue([]);
    vi.mocked(postRefresh).mockResolvedValue();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps a status error visible and retries polling", async () => {
    vi.useFakeTimers();
    vi.mocked(fetchStatus)
      .mockRejectedValueOnce(new Error("backend unavailable"))
      .mockResolvedValue(idleStatus);

    const { result } = renderHook(() => useDashboard(2026));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.error).toBe("backend unavailable");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(fetchStatus).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });

  it("disables refresh immediately while the POST is pending", async () => {
    vi.mocked(fetchStatus).mockResolvedValue(idleStatus);
    let release: (() => void) | undefined;
    vi.mocked(postRefresh).mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );

    const { result } = renderHook(() => useDashboard(2026));
    await waitFor(() => expect(result.current.status).toEqual(idleStatus));

    act(() => {
      void result.current.startRefresh(false);
    });
    expect(result.current.requestingRefresh).toBe(true);

    await act(async () => {
      release?.();
    });
    await waitFor(() => expect(result.current.requestingRefresh).toBe(false));
  });
});
