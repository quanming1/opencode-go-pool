import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";

// ECharts 依赖 canvas，jsdom 无法渲染——测试中 mock 掉图表组件，
// 只验证页面结构（图表渲染的正确性由 dev 手动目检，见 PRD-A3 测试计划）。
vi.mock("../features/demo/DemoChart", () => ({
  DemoChart: () => <div data-testid="demo-chart" />,
}));

describe("App", () => {
  it("renders header with project name and version", () => {
    render(<App />);
    expect(screen.getByText("OpenCode Go Pool")).toBeDefined();
    expect(screen.getByText("v0.1.0")).toBeDefined();
  });

  it("renders welcome card and demo chart placeholder", () => {
    render(<App />);
    expect(screen.getByText(/多个 OpenCode Go 订阅账号/)).toBeDefined();
    expect(screen.getByTestId("demo-chart")).toBeDefined();
  });
});
