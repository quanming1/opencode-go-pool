import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountCard } from "./AccountCard";
import type { AccountQuota, PoolAccount } from "../../types/pool";
import { I18nProvider } from "../../i18n";

const account: PoolAccount = {
  id: "a1",
  name: "账号 A",
  status: "healthy",
  cooldown_until: null,
  cooldown_seconds_remaining: null,
  last_error: null,
  error_count: 0,
  consecutive_failures: 0,
  enabled: true,
};

const quota: AccountQuota = {
  account_id: "a1",
  error: null,
  quota: {
    rolling: {
      status: "ok",
      percent: 2,
      resets_at: "2026-08-20T14:09:31Z",
      resets_in_seconds: 57 * 60,
    },
    weekly: {
      status: "rate-limited",
      percent: 100,
      resets_at: "2026-08-24T00:00:00Z",
      resets_in_seconds: 3 * 86400 + 18 * 3600,
    },
    monthly: {
      status: "ok",
      percent: 50,
      resets_at: "2026-09-19T05:54:29Z",
      resets_in_seconds: 30 * 86400,
    },
  },
};

describe("AccountCard C5 额度", () => {
  it("展示滚动/每周/每月百分比与重置时间", () => {
    render(<I18nProvider><AccountCard account={account} quota={quota} /></I18nProvider>);
    expect(screen.getByTestId("quota-block")).toBeDefined();
    expect(screen.getByText("滚动额度")).toBeDefined();
    expect(screen.getByText("已用 2%")).toBeDefined();
    expect(screen.getByText("重置于 57 分钟")).toBeDefined();
    expect(screen.getByText("已限额")).toBeDefined();
    expect(screen.getByText("重置于 3 天 18 小时")).toBeDefined();
    expect(screen.getByText("已用 50%")).toBeDefined();
    expect(screen.getByText("重置于 30 天 0 小时")).toBeDefined();
    expect(document.querySelector(".quota-row__fill--danger")).not.toBeNull();
  });

  it("额度失败显示额度未知", () => {
    render(<I18nProvider><AccountCard account={account} quota={{ account_id: "a1", quota: null, error: "http 401" }} /></I18nProvider>);
    expect(screen.getByText("额度未知（http 401）")).toBeDefined();
  });

  it("尚未返回额度时不渲染额度区块", () => {
    render(<I18nProvider><AccountCard account={account} /></I18nProvider>);
    expect(screen.queryByTestId("quota-block")).toBeNull();
  });
});
