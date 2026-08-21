import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
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
    per_account_models: [],
    buckets: [],
  },
  quota: {
    accounts: [],
    summary: {
      total_accounts: 1,
      queried: 1,
      ok_accounts: 1,
      rolling_available: 1,
      rolling_avg_percent: 5,
      weekly_avg_percent: 20,
      monthly_avg_percent: 30,
      allocated_usd: { rolling: 12, weekly: 30, monthly: 60 },
      estimated_used_usd: { rolling: 1, weekly: 6, monthly: 18 },
    },
    fetched_at: "2026-08-20T09:00:00+00:00",
    cached: false,
  },
};

// mock 四个 service（D1：事件已从轮询中移除，改为 EventTimeline 自管分页）
vi.mock("../../services/api", () => ({
  fetchAccounts: vi.fn(),
  fetchStats: vi.fn(),
  fetchQuota: vi.fn(),
  fetchLogsOverview: vi.fn(),
}));

import {
  fetchAccounts,
  fetchLogsOverview,
  fetchQuota,
  fetchStats,
} from "../../services/api";

const mFetchAccounts = vi.mocked(fetchAccounts);
const mFetchStats = vi.mocked(fetchStats);
const mFetchQuota = vi.mocked(fetchQuota);
const mFetchLogsOverview = vi.mocked(fetchLogsOverview);

const overviewSample = {
  current_active: { account_id: "a1", last_success_at: "2026-08-20T09:00:00+00:00" },
  rate: { minutes: 60, requests_per_minute: 0.5, tokens_per_hour: 100 },
  usage_remaining: {
    estimated_requests_left: 1000,
    estimated_hours_left: 33.3,
    basis: "rolling_percent_and_local_rate",
    note: "估算口径",
  },
};

describe("useAccountPolling", () => {
  it("拉取四个接口并进入非 loading 态", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockResolvedValue(sample.quota);
    mFetchLogsOverview.mockResolvedValue(overviewSample);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(mFetchAccounts).toHaveBeenCalled());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.accounts).toEqual(sample.accounts);
    expect(result.current.stats?.totals.request_count).toBe(1);
    expect(result.current.quota?.summary.rolling_avg_percent).toBe(5);
    expect(result.current.overview?.current_active?.account_id).toBe("a1");
    expect(result.current.quotaError).toBeNull();
    expect(result.current.overviewError).toBeNull();
    unmount();
  });

  it("核心接口失败时置 error 且不再 loading", async () => {
    mFetchAccounts.mockRejectedValue(new Error("boom"));
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockResolvedValue(sample.quota);
    mFetchLogsOverview.mockResolvedValue(overviewSample);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.loading).toBe(false);
    expect(result.current.quotaError).toBeNull();
    unmount();
  });

  it("额度接口失败只显示 quotaError，不阻断核心数据", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockRejectedValue(new Error("quota down"));
    mFetchLogsOverview.mockResolvedValue(overviewSample);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.accounts).toEqual(sample.accounts);
    expect(result.current.quota).toBeNull();
    expect(result.current.quotaError).toBe("quota down");
    unmount();
  });

  it("overview 接口失败只显示 overviewError，不阻断核心数据", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockResolvedValue(sample.quota);
    mFetchLogsOverview.mockRejectedValue(new Error("overview down"));

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.quotaError).toBeNull();
    expect(result.current.overview).toBeNull();
    expect(result.current.overviewError).toBe("overview down");
    unmount();
  });

  it("切换统计周期后 fetchStats 带新 hours，且 statsHours 更新", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockResolvedValue(sample.quota);
    mFetchLogsOverview.mockResolvedValue(overviewSample);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mFetchStats).toHaveBeenLastCalledWith(24);

    await act(async () => {
      result.current.setStatsHours(168);
    });
    await waitFor(() => expect(mFetchStats).toHaveBeenLastCalledWith(168));
    expect(result.current.statsHours).toBe(168);
    unmount();
  });

  it("强制刷新额度传 force=true，失败保留旧数据", async () => {
    mFetchAccounts.mockResolvedValue(sample.accounts);
    mFetchStats.mockResolvedValue(sample.stats);
    mFetchQuota.mockResolvedValue(sample.quota);
    mFetchLogsOverview.mockResolvedValue(overviewSample);

    const { result, unmount } = renderHook(() => useAccountPolling(50));
    await waitFor(() => expect(result.current.loading).toBe(false));
    mFetchQuota.mockRejectedValueOnce(new Error("refresh failed"));

    let message: string | null = null;
    await act(async () => {
      message = await result.current.forceRefreshQuota();
    });
    expect(message).toBe("refresh failed");
    expect(mFetchQuota).toHaveBeenLastCalledWith(true);
    expect(result.current.quota).toEqual(sample.quota);
    expect(result.current.quotaError).toBe("refresh failed");
    unmount();
  });
});
