import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SwitchTimeline } from "./SwitchTimeline";
import type { SwitchEvent } from "../../types/pool";

const events: SwitchEvent[] = [
  { ts: "2026-08-20T09:00:00", account_id: "a2", kind: "quota", reason: "rate limit", kind_label: "额度限制" },
  { ts: "2026-08-20T09:05:00", account_id: "a1", kind: "recover", reason: null, kind_label: "恢复" },
];

describe("SwitchTimeline", () => {
  it("渲染事件列表：账号 + 中文 kind_label + 原因", () => {
    render(<SwitchTimeline events={events} />);
    expect(screen.getByText("a2")).toBeDefined();
    expect(screen.getByText("额度限制")).toBeDefined();
    expect(screen.getByText("rate limit")).toBeDefined();
    expect(screen.getByText("恢复")).toBeDefined();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("空事件显示空态文案", () => {
    render(<SwitchTimeline events={[]} />);
    expect(screen.getByText(/暂无轮换事件/)).toBeDefined();
  });
});
