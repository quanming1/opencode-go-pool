import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";

// Dashboard 依赖轮询 hook → 直接 mock 掉，App 只验证页头结构
vi.mock("../features/dashboard/useAccountPolling", () => ({
  useAccountPolling: () => ({ accounts: [], error: null, loading: false }),
}));

describe("App", () => {
  it("renders header with project name and version", () => {
    render(<App />);
    expect(screen.getByText("OpenCode Go Pool")).toBeDefined();
    expect(screen.getByText("v0.1.0")).toBeDefined();
  });

  it("renders dashboard empty state", () => {
    render(<App />);
    expect(screen.getByText(/暂无账号/)).toBeDefined();
  });
});
