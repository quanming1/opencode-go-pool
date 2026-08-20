import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SummaryCards } from "./SummaryCards";
import type { PoolAccount, QuotaSummary } from "../../types/pool";

const accounts: PoolAccount[] = [
  {
    id: "a1",
    name: "A1",
    status: "healthy",
    cooldown_until: null,
    cooldown_seconds_remaining: null,
    last_error: null,
    error_count: 0,
    consecutive_failures: 0,
    enabled: true,
  },
];

const summary: QuotaSummary = {
  total_accounts: 3,
  queried: 3,
  ok_accounts: 3,
  rolling_available: 2,
  rolling_avg_percent: 18,
  weekly_avg_percent: 60,
  monthly_avg_percent: 42,
  allocated_usd: { rolling: 36, weekly: 90, monthly: 180 },
  estimated_used_usd: { rolling: 6, weekly: 54, monthly: 76 },
};

describe("SummaryCards C5 额度总览", () => {
  it("展示额度可用账号数、总额度估算与三个窗口均值", () => {
    render(<SummaryCards accounts={accounts} quotaSummary={summary} />);
    expect(screen.getByTestId("summary-quota")).toBeDefined();
    expect(screen.getByTestId("summary-quota-available")).toHaveTextContent("2/3");
    expect(screen.getByText("额度可用")).toBeDefined();
    expect(screen.getByText(/估算 \$6 \/ 总额 \$36/)).toBeDefined();
    expect(screen.getByText(/估算 \$54 \/ 总额 \$90/)).toBeDefined();
    expect(screen.getByText(/估算 \$76 \/ 总额 \$180/)).toBeDefined();
    expect(screen.getByText("18%")).toBeDefined();
    expect(screen.getByText("60%")).toBeDefined();
    expect(screen.getByText("42%")).toBeDefined();
  });

  it("无额度数据时不展示额度总览卡", () => {
    render(<SummaryCards accounts={accounts} />);
    expect(screen.queryByTestId("summary-quota")).toBeNull();
  });
});
