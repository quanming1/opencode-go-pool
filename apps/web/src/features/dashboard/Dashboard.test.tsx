import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Dashboard } from "./Dashboard";
import { useAccountPolling } from "./useAccountPolling";
import type { PoolAccount } from "../../types/pool";

const sample: PoolAccount[] = [
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
  },
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
  },
];

// mock 轮询 hook：避免真实网络与计时器
vi.mock("./useAccountPolling", () => ({
  useAccountPolling: vi.fn(),
}));

const mockedHook = vi.mocked(useAccountPolling);

describe("Dashboard", () => {
  it("渲染统计摘要（1 可用 / 1 冷却中 / 0 禁用）与账号列表", () => {
    mockedHook.mockReturnValue({ accounts: sample, error: null, loading: false });
    render(<Dashboard />);

    expect(screen.getByTestId("summary-available").textContent).toBe("1");
    expect(screen.getByTestId("summary-cooldown").textContent).toBe("1");
    expect(screen.getByTestId("summary-disabled").textContent).toBe("0");
    expect(screen.getAllByTestId("account-card")).toHaveLength(2);
  });

  it("空账号显示空态文案", () => {
    mockedHook.mockReturnValue({ accounts: [], error: null, loading: false });
    render(<Dashboard />);
    expect(screen.getByText(/暂无账号/)).toBeDefined();
  });

  it("错误时显示警告但保留数据", () => {
    mockedHook.mockReturnValue({ accounts: sample, error: "network down", loading: false });
    render(<Dashboard />);
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getAllByTestId("account-card")).toHaveLength(2);
  });

  it("加载中显示占位", () => {
    mockedHook.mockReturnValue({ accounts: [], error: null, loading: true });
    render(<Dashboard />);
    expect(screen.getByText(/加载中/)).toBeDefined();
  });
});

// 对 hook 本身的行为断言放在独立文件 useAccountPolling.test.ts，
// 不与本文件的 vi.mock 冲突。
