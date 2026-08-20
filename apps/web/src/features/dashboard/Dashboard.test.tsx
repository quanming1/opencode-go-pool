import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Dashboard } from "./Dashboard";
import { useAccountPolling } from "./useAccountPolling";

// mock 轮询 hook + 图表组件（echarts 依赖 canvas，jsdom 无法执行）
vi.mock("./useAccountPolling", () => ({
  useAccountPolling: vi.fn(),
}));
vi.mock("../charts/UsageCharts", () => ({
  UsageCharts: () => <div data-testid="usage-chart" />,
}));

const mockedHook = vi.mocked(useAccountPolling);
const sample = {
  accounts: [
    {
      id: "a1",
      name: "账号A",
      status: "healthy",
      cooldown_until: null,
      cooldown_seconds_remaining: null,
      last_error: null,
      error_count: 0,
      consecutive_failures: 0,
      enabled: true,
    } as const,
    {
      id: "a2",
      name: "账号B",
      status: "cooldown",
      cooldown_until: "2026-08-19T12:00:00",
      cooldown_seconds_remaining: 60,
      last_error: "quota",
      error_count: 1,
      consecutive_failures: 1,
      enabled: true,
    } as const,
  ],
  stats: {
    hours: 24,
    totals: { request_count: 5, prompt_tokens: 100, completion_tokens: 40, error_count: 1 },
    per_account: [],
    buckets: [
      { ts: "2026-08-20T08:00:00", request_count: 5, prompt_tokens: 100, completion_tokens: 40, error_count: 1 },
    ],
  },
  switchEvents: [
    { ts: "2026-08-20T09:00:00", account_id: "a2", kind: "quota", reason: "rate limit", kind_label: "额度限制" },
  ],
};

describe("Dashboard", () => {
  it("渲染统计摘要（1 可用 / 1 冷却中 / 0 禁用）与账号列表", () => {
    mockedHook.mockReturnValue({ ...sample, error: null, loading: false });
    render(<Dashboard />);

    expect(screen.getByTestId("summary-available").textContent).toBe("1");
    expect(screen.getByTestId("summary-cooldown").textContent).toBe("1");
    expect(screen.getByTestId("summary-disabled").textContent).toBe("0");
    expect(screen.getAllByTestId("account-card")).toHaveLength(2);
  });

  it("渲染用量趋势图与轮换事件区块", () => {
    mockedHook.mockReturnValue({ ...sample, error: null, loading: false });
    render(<Dashboard />);
    expect(screen.getByTestId("usage-chart")).toBeDefined();
    expect(screen.getByText("用量趋势（近24h）")).toBeDefined();
    expect(screen.getByText("轮换事件")).toBeDefined();
    expect(screen.getByText("额度限制")).toBeDefined();
  });

  it("空账号显示空态文案", () => {
    mockedHook.mockReturnValue({
      accounts: [],
      stats: sample.stats,
      switchEvents: [],
      error: null,
      loading: false,
    });
    render(<Dashboard />);
    expect(screen.getByText(/暂无账号/)).toBeDefined();
  });

  it("错误时显示警告但保留数据", () => {
    mockedHook.mockReturnValue({ ...sample, error: "network down", loading: false });
    render(<Dashboard />);
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getAllByTestId("account-card")).toHaveLength(2);
  });

  it("加载中显示占位", () => {
    mockedHook.mockReturnValue({
      accounts: [],
      stats: null,
      switchEvents: [],
      error: null,
      loading: true,
    });
    render(<Dashboard />);
    expect(screen.getByText(/加载中/)).toBeDefined();
  });
});
