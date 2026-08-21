import { describe, expect, it } from "vitest";
import { bucketLabel, bucketSuccessRates } from "./chartData";
import type { StatsResponse, UsageBucket } from "../../types/pool";

function makeStats(buckets: UsageBucket[], hours = 24): StatsResponse {
  return {
    hours,
    totals: {
      request_count: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      error_count: 0,
    },
    per_account: [],
    per_account_models: [],
    buckets,
  };
}

describe("bucketLabel（E5 周期标签自适应）", () => {
  it("≤48h 显示 HH:MM", () => {
    expect(bucketLabel("2026-08-21T08:30:00", 24)).toBe("08:30");
  });
  it(">48h 显示 MM-DD HH:MM", () => {
    expect(bucketLabel("2026-08-21T08:30:00", 168)).toBe("08-21 08:30");
  });
});

describe("bucketSuccessRates（E5 小时级成功率）", () => {
  it("新后端：使用 success_count 计算百分比", () => {
    const stats = makeStats([
      { ts: "2026-08-21T08:00:00", request_count: 4, prompt_tokens: 0, completion_tokens: 0, error_count: 1, success_count: 3 },
    ]);
    const rows = bucketSuccessRates(stats);
    expect(rows[0].rate).toBe(75); // 3/4 = 0.75
  });

  it("旧后端：无 success_count 时回退 request_count - error_count", () => {
    const stats = makeStats([
      { ts: "2026-08-21T08:00:00", request_count: 10, prompt_tokens: 0, completion_tokens: 0, error_count: 2 },
    ]);
    expect(bucketSuccessRates(stats)[0].rate).toBe(80); // (10-2)/10 = 0.8
  });

  it("无请求的桶为 null（断点，不显示）", () => {
    const stats = makeStats([
      { ts: "2026-08-21T08:00:00", request_count: 0, prompt_tokens: 0, completion_tokens: 0, error_count: 0 },
    ]);
    expect(bucketSuccessRates(stats)[0].rate).toBeNull();
  });
});
