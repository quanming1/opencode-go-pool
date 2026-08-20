import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EventTimeline } from "./EventTimeline";
import { buildSummary } from "./eventSummary";
import type { EventItem } from "../../types/pool";

const events: EventItem[] = [
  {
    type: "request",
    data: {
      success: true,
      protocol: "responses",
      model: "gpt-5.6-luna",
      status_code: 200,
      duration_ms: 42,
      attempt_count: 1,
      account_id: "a1",
      token: { prompt: 7, completion: 3 },
    },
    meta: { source: "forwarder", request_id: "r1" },
    time: "2026-08-20T09:00:00+00:00",
  },
  {
    type: "key_switch",
    data: { from_account_id: "a1", to_account_id: "a2", error_type: "quota" },
    meta: { source: "forwarder", request_id: "r1" },
    time: "2026-08-20T09:01:00+00:00",
  },
  {
    type: "all_keys_invalid",
    data: {
      attempted_account_ids: ["a1", "a2"],
      error_types: ["quota"],
      attempt_count: 2,
    },
    meta: { source: "forwarder" },
    time: "2026-08-20T09:02:00+00:00",
  },
];

describe("EventTimeline", () => {
  it("渲染事件列表：中文类型徽章 + 摘要", () => {
    render(<EventTimeline events={events} />);
    // 三种类型标签
    expect(screen.getByText("请求")).toBeDefined();
    expect(screen.getByText("切换")).toBeDefined();
    expect(screen.getByText("全部额度/鉴权失效")).toBeDefined();
    // 请求摘要含成功/协议/模型/耗时/尝试链
    expect(screen.getByText(/成功 responses gpt-5.6-luna HTTP 200 42ms 尝试 1 次 tok 7\/3/)).toBeDefined();
    // 切换摘要 from → to
    expect(screen.getByText("a1 → a2（quota）")).toBeDefined();
    // 全部失效摘要含账号与类型
    expect(screen.getByText(/a1, a2，错误类型 quota/)).toBeDefined();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("空事件显示空态文案", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText(/暂无事件/)).toBeDefined();
  });
});

describe("buildSummary", () => {
  it("失败请求显示失败与错误", () => {
    const s = buildSummary("request", {
      success: false,
      status_code: 400,
      duration_ms: 5,
      attempt_count: 0,
      error: { type: "bad_request", message: "bad model" },
    });
    expect(s).toContain("失败");
    expect(s).toContain("HTTP 400");
  });

  it("冷启动/恢复/控制事件摘要", () => {
    expect(buildSummary("key_cooldown_started", { account_id: "a1", error_type: "quota", reason: "rate limit" })).toBe("a1（quota）：rate limit");
    expect(buildSummary("key_cooldown_completed", { account_id: "a1", previous_status: "cooldown" })).toBe("a1（原 cooldown）：已恢复");
    expect(buildSummary("key_disabled", { account_id: "a1", automatic: true, reason: "auto-disabled" })).toBe("a1（自动）：auto-disabled");
    expect(buildSummary("gateway_key_created", { key_id: 7, label: "ftre" })).toBe("#7（ftre）");
  });

  it("未知类型回退为原始 JSON", () => {
    expect(buildSummary("weird_type", { a: 1 })).toBe('{"a":1}');
  });
});