import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAccountPolling } from "./useAccountPolling";

const sample = {
  accounts: [
    {
      id: "a1",
      name: "账号A",
      status: "healthy" as const,
      cooldown_until: null,
      cooldown_seconds_remaining: null,
      last_error: null,
      error_count: 0,
      consecutive_failures: 0,
      enabled: true,
    },
  ],
  stats: {
    hours: 24,
    totals: { request_count: 1, prompt_tokens: 10, completion_tokens: 5, error_count: 0 },
    per_account: [],
    buckets: [],
  },
  switchEvents: [],
};

// mock 三个 service
vi.mock("../../services/api", () => ({
  fetchAccounts: vi.fn(),
  fetchStats: vi.fn(),
  fetchSwitchHistory: vi.fn(),
}));

import {
  fetchAccounts,
  fetchStats,
  fetchSwitchHistory,
} from "../../services/api";

const mFetchAccounts = vi.mocked(fetchAccounts);
const mFetchStats = vi.mocked(fetchStats);
const mFetchSwitchHistory = vi.mocked(fetchSwitchHistory);

describe("useAccountPolling", () => {
  it("拉取三个接口并进入非 loading 态", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchSwitchHistory.mockResolvedValue([]);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(mFetchAccounts).toHaveBeenCalled());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.accounts).toEqual(sample.accounts);
    expect(result.current.stats?.totals.request_count).toBe(1);
    unmount();
  });

  it("任一接口失败时置 error 且不再 loading", async () => {
    mFetchAccounts.mockRejectedValue(new Error("boom"));
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchSwitchHistory.mockResolvedValue([]);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.loading).toBe(false);
    unmount();
  });
});
