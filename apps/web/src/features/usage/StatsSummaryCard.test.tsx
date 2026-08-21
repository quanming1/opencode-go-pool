import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { StatsSummaryCard } from "./StatsSummaryCard";
import type { StatsResponse } from "../../types/pool";

function makeStats(): StatsResponse {
  return {
    hours: 24,
    totals: {
      request_count: 120,
      prompt_tokens: 1000,
      completion_tokens: 900,
      error_count: 3,
      success_count: 117,
      success_rate: 0.975,
    },
    per_account: [
      {
        account_id: "a1",
        request_count: 120,
        prompt_tokens: 1000,
        completion_tokens: 900,
        error_count: 3,
        success_count: 117,
      },
    ],
    per_account_models: [
      {
        account_id: "a1",
        model: "m-a",
        request_count: 100,
        prompt_tokens: 800,
        completion_tokens: 700,
        error_count: 1,
        success_count: 99,
      },
      {
        account_id: "a1",
        model: "m-b",
        request_count: 20,
        prompt_tokens: 200,
        completion_tokens: 200,
        error_count: 2,
        success_count: 18,
      },
    ],
    buckets: [],
    error_types: [{ type: "quota", count: 3 }],
    summary: {
      window: 500,
      duration_ms: { avg: 812, p95: 2450, max: 4800 },
      protocol: [
        { name: "responses", count: 80 },
        { name: "chat/completions", count: 40 },
      ],
      event_counts: {
        key_switch: 1,
        key_cooldown_started: 0,
        key_disabled: 0,
        all_keys_unavailable: 0,
        all_keys_invalid: 0,
      },
    },
  };
}

const valueText = (testid: string): string =>
  screen.getByTestId(testid).textContent ?? "";

describe("StatsSummaryCard（E4 运行汇总）", () => {
  it("渲染六项运行汇总（请求/成功率/Token/耗时/模型/账号）", () => {
    render(
      <I18nProvider>
        <StatsSummaryCard stats={makeStats()} />
      </I18nProvider>,
    );
    expect(valueText("summary-requests")).toContain("120");
    expect(valueText("summary-success-rate")).toContain("97.5%");
    expect(valueText("summary-tokens")).toContain("1,900");
    expect(valueText("summary-avg-duration")).toContain("812");
    expect(valueText("summary-active-models")).toContain("2");
    expect(valueText("summary-active-accounts")).toContain("1");
  });

  it("旧后端/旧数据容错：缺 summary 与 success 字段不崩溃，耗时显示占位", () => {
    const stats = makeStats();
    // 模拟旧后端：无 summary、无 success_count/success_rate（新字段均为可选，直接删除）
    delete stats.summary;
    const totals = stats.totals;
    delete totals.success_count;
    delete totals.success_rate;
    render(
      <I18nProvider>
        <StatsSummaryCard stats={stats} />
      </I18nProvider>,
    );
    expect(valueText("summary-avg-duration")).toContain("暂无");
    // 旧后端有请求但无 success_rate 数据时，成功率显示占位而非误导的 0%
    expect(valueText("summary-success-rate")).toContain("暂无");
  });

  it("统计不到模型/账号时显示 0", () => {
    const stats = makeStats();
    stats.per_account_models = [];
    stats.per_account = [];
    render(
      <I18nProvider>
        <StatsSummaryCard stats={stats} />
      </I18nProvider>,
    );
    expect(valueText("summary-active-models")).toContain("0");
    expect(valueText("summary-active-accounts")).toContain("0");
  });
});
