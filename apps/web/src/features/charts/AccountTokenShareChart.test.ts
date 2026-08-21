import { describe, expect, it } from "vitest";
import { accountTokenShare } from "./chartData";
import type { PerAccountUsage, StatsResponse } from "../../types/pool";

function makeStats(perAccount: PerAccountUsage[]): StatsResponse {
  return {
    hours: 24,
    totals: {
      request_count: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      error_count: 0,
    },
    per_account: perAccount,
    per_account_models: [],
    buckets: [],
  };
}

describe("accountTokenShare（E5 账号 Token 占比）", () => {
  it("按 token（prompt+completion）降序，过滤零 token 账号", () => {
    const stats = makeStats([
      { account_id: "a1", request_count: 3, prompt_tokens: 100, completion_tokens: 50, error_count: 0 }, // 150
      { account_id: "a2", request_count: 1, prompt_tokens: 0, completion_tokens: 0, error_count: 0 }, // 0 -> 过滤
      { account_id: "a3", request_count: 5, prompt_tokens: 300, completion_tokens: 100, error_count: 1 }, // 400
    ]);
    const rows = accountTokenShare(stats);
    expect(rows.map((r) => r.account)).toEqual(["a3", "a1"]);
    expect(rows[0]).toMatchObject({ account: "a3", tokens: 400, requests: 5 });
    expect(rows[1]).toMatchObject({ account: "a1", tokens: 150, requests: 3 });
  });

  it("全部无 token 时返回空数组", () => {
    const stats = makeStats([
      { account_id: "a1", request_count: 1, prompt_tokens: 0, completion_tokens: 0, error_count: 0 },
    ]);
    expect(accountTokenShare(stats)).toEqual([]);
  });
});
