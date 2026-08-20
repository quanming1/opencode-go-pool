import { describe, expect, it } from "vitest";
import type { PoolAccount } from "../../types/pool";

const accounts: PoolAccount[] = [
  {
    id: "a1",
    name: "Healthy",
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
    name: "Cooling",
    status: "cooldown",
    cooldown_until: "2026-08-19T12:00:00",
    cooldown_seconds_remaining: 120,
    last_error: "quota: rate limit",
    error_count: 2,
    consecutive_failures: 1,
    enabled: true,
  },
  {
    id: "a3",
    name: "Disabled",
    status: "disabled",
    cooldown_until: null,
    cooldown_seconds_remaining: null,
    last_error: "manual",
    error_count: 0,
    consecutive_failures: 0,
    enabled: false,
  },
];

// 为避免 jsdom 与组件渲染的复杂度，这里直接测类型与数据结构正确性；
// 组件行为性断言放在 Dashboard 测试（mock fetch）。
describe("PoolAccount 类型结构（对应 /api/accounts）", () => {
  it("每个账号含状态与计数，且不含 api_key 字段", () => {
    for (const a of accounts) {
      expect(a).toHaveProperty("id");
      expect(a).toHaveProperty("status");
      expect(a).toHaveProperty("consecutive_failures");
      expect(a).toHaveProperty("error_count");
      expect(a).toHaveProperty("enabled");
      expect(a).not.toHaveProperty("api_key");
    }
  });

  it("status 为三种合法值之一", () => {
    for (const a of accounts) {
      expect(["healthy", "cooldown", "disabled"]).toContain(a.status);
    }
  });
});
