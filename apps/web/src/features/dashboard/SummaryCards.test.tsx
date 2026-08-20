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
  it("将账号状态收进紧凑状态框，并展示三条总额度进度条", () => {
    const accountsWithStatuses: PoolAccount[] = [
      accounts[0],
      {
        ...accounts[0],
        id: "a2",
        status: "cooldown",
      },
      {
        ...accounts[0],
        id: "a3",
        status: "disabled",
        enabled: false,
      },
    ];

    render(<SummaryCards accounts={accountsWithStatuses} quotaSummary={summary} />);

    expect(screen.getByTestId("summary-status")).toBeDefined();
    expect(screen.getByTestId("summary-available")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-cooldown")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-disabled")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-quota")).toBeDefined();
    expect(screen.getByTestId("summary-quota-available")).toHaveTextContent("2/3");
    expect(screen.getByTestId("summary-quota-bar-rolling")).toHaveAttribute(
      "aria-valuenow",
      "17",
    );
    expect(screen.getByTestId("summary-quota-bar-weekly")).toHaveAttribute(
      "aria-valuenow",
      "60",
    );
    expect(screen.getByTestId("summary-quota-bar-monthly")).toHaveAttribute(
      "aria-valuenow",
      "42",
    );
    expect(screen.getByText("估算 $6")).toBeDefined();
    expect(screen.getByText("总额 $36")).toBeDefined();
    expect(screen.getByText("估算 $54")).toBeDefined();
    expect(screen.getByText("总额 $90")).toBeDefined();
    expect(screen.getByText("估算 $76")).toBeDefined();
    expect(screen.getByText("总额 $180")).toBeDefined();
    expect(screen.getAllByText("18%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("42%").length).toBeGreaterThan(0);
  });

  it("无额度数据时保留状态框且不展示额度总览卡", () => {
    render(<SummaryCards accounts={accounts} />);
    expect(screen.getByTestId("summary-status")).toBeDefined();
    expect(screen.queryByTestId("summary-quota")).toBeNull();
  });
});
