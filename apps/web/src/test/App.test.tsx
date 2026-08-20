import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import App from "../App";

// 面板级 mock：App 只验证布局与 tab 切换
vi.mock("../features/usage/UsagePanel", () => ({
  UsagePanel: () => <div data-testid="usage-panel" />,
}));
vi.mock("../features/keys/KeysPanel", () => ({
  KeysPanel: () => <div data-testid="keys-panel" />,
}));

describe("App 分栏布局与 Tab 切换", () => {
  it("渲染页头与左侧 tab 导航", () => {
    render(<App />);
    expect(screen.getByText("OpenCode Go Pool")).toBeDefined();
    expect(screen.getByTestId("sidebar")).toBeDefined();
    expect(screen.getByTestId("tab-usage")).toBeDefined();
    expect(screen.getByTestId("tab-keys")).toBeDefined();
  });

  it("默认显示用量信息 tab，切换后显示 key 管理", () => {
    render(<App />);
    expect(screen.getByTestId("usage-panel")).toBeDefined();

    fireEvent.click(screen.getByTestId("tab-keys"));
    expect(screen.getByTestId("keys-panel")).toBeDefined();
    expect(screen.queryByTestId("usage-panel")).toBeNull();
  });
});
