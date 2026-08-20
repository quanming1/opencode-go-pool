import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EventTimeline } from "./EventTimeline";
import { buildSummary } from "./eventSummary";
import type { EventItem, EventsResponse } from "../../types/pool";

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
];

const page2: EventItem[] = [
  {
    type: "all_keys_invalid",
    data: {
      attempted_account_ids: ["a1", "a2"],
      error_types: ["quota"],
      attempt_count: 2,
    },
    meta: { source: "forwarder" },
    time: "2026-08-20T08:00:00+00:00",
  },
];

vi.mock("../../services/api", () => ({
  fetchEventsPage: vi.fn(),
}));

import { fetchEventsPage } from "../../services/api";

const mFetchEventsPage = vi.mocked(fetchEventsPage);

function pageBody(items: EventItem[], offset: number, has_more: boolean): EventsResponse {
  return { events: items, offset, has_more };
}

describe("EventTimeline", () => {
  it("加载第一页并渲染类型徽章与摘要", async () => {
    mFetchEventsPage.mockResolvedValue(pageBody(events, 0, true));
    render(<EventTimeline />);
    await waitFor(() => expect(mFetchEventsPage).toHaveBeenCalledWith(20, 0));
    expect(screen.getByText("请求")).toBeDefined();
    expect(screen.getByText("切换")).toBeDefined();
    expect(
      screen.getByText(/成功 responses gpt-5.6-luna HTTP 200 42ms 尝试 1 次 tok 7\/3/),
    ).toBeDefined();
    expect(screen.getByText("a1 → a2（quota）")).toBeDefined();
  });

  it("空页显示空态", async () => {
    mFetchEventsPage.mockResolvedValue(pageBody([], 0, false));
    render(<EventTimeline />);
    await waitFor(() => expect(screen.getByText(/暂无事件/)).toBeDefined());
  });

  it("下一页/上一页按 offset 翻页，末页禁用下一页", async () => {
    mFetchEventsPage.mockResolvedValue(pageBody(events, 0, true));
    render(<EventTimeline />);
    await waitFor(() => screen.getByText("请求"));

    // 第二页
    mFetchEventsPage.mockResolvedValue(pageBody(page2, 20, false));
    fireEvent.click(screen.getByTestId("events-next"));
    await waitFor(() =>
      expect(mFetchEventsPage).toHaveBeenLastCalledWith(20, 20),
    );
    expect(screen.getByText("全部额度/鉴权失效")).toBeDefined();
    // 末页：下一页禁用
    expect(screen.getByTestId("events-next")).toBeDisabled();

    // 回到第一页
    mFetchEventsPage.mockResolvedValue(pageBody(events, 0, true));
    fireEvent.click(screen.getByTestId("events-prev"));
    await waitFor(() =>
      expect(mFetchEventsPage).toHaveBeenLastCalledWith(20, 0),
    );
    expect(screen.getByText("请求")).toBeDefined();
  });

  it("字段详情：meta 与 data 同名字段（request_id）只渲染一次", async () => {
    // request 事件 data 与 meta 都含 request_id（真实转发即如此）
    mFetchEventsPage.mockResolvedValue(
      pageBody(
        [
          {
            type: "request",
            data: { success: true, request_id: "r1", account_id: "a1" },
            meta: { source: "forwarder", request_id: "r1" },
            time: "2026-08-20T09:00:00+00:00",
          },
        ],
        0,
        false,
      ),
    );
    render(<EventTimeline />);
    await waitFor(() => screen.getByText("请求"));
    fireEvent.click(screen.getByText("字段详情"));
    // request_id 行只出现一次（React key 不冲突）
    const fields = screen.getAllByText("request_id");
    expect(fields).toHaveLength(1);
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
    expect(
      buildSummary("key_cooldown_started", {
        account_id: "a1",
        error_type: "quota",
        reason: "rate limit",
      }),
    ).toBe("a1（quota）：rate limit");
    expect(
      buildSummary("key_cooldown_completed", {
        account_id: "a1",
        previous_status: "cooldown",
      }),
    ).toBe("a1（原 cooldown）：已恢复");
    expect(
      buildSummary("key_disabled", {
        account_id: "a1",
        automatic: true,
        reason: "auto-disabled",
      }),
    ).toBe("a1（自动）：auto-disabled");
    expect(buildSummary("gateway_key_created", { key_id: 7, label: "ftre" })).toBe(
      "#7（ftre）",
    );
  });

  it("未知类型回退为原始 JSON", () => {
    expect(buildSummary("weird_type", { a: 1 })).toBe('{"a":1}');
  });
});
