import type { PoolAccount, QuotaSummary } from "../../types/pool";
import { quotaTone } from "./quotaFormat";

const QUOTA_ROWS = [
  {
    key: "rolling",
    label: "滚动额度",
    averageKey: "rolling_avg_percent",
    averageLabel: "滚动均值",
    testId: "summary-quota-bar-rolling",
  },
  {
    key: "weekly",
    label: "每周额度",
    averageKey: "weekly_avg_percent",
    averageLabel: "每周均值",
    testId: "summary-quota-bar-weekly",
  },
  {
    key: "monthly",
    label: "每月额度",
    averageKey: "monthly_avg_percent",
    averageLabel: "每月均值",
    testId: "summary-quota-bar-monthly",
  },
] as const;

function quotaUsagePercent(
  summary: QuotaSummary,
  key: (typeof QUOTA_ROWS)[number]["key"],
): number {
  const used = summary.estimated_used_usd[key];
  const allocated = summary.allocated_usd[key];
  if (!Number.isFinite(used) || !Number.isFinite(allocated) || allocated <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, Math.round((used / allocated) * 100)));
}

function StatusMetric({
  count,
  label,
  tone,
  testId,
}: {
  count: number;
  label: string;
  tone: "available" | "cooldown" | "disabled";
  testId: string;
}) {
  return (
    <div className={`summary-status__item summary-status__item--${tone}`}>
      <div className="summary-status__num" data-testid={testId}>
        {count}
      </div>
      <div className="summary-status__label">{label}</div>
    </div>
  );
}

function AccountStatus({
  total,
  available,
  cooling,
  disabled,
}: {
  total: number;
  available: number;
  cooling: number;
  disabled: number;
}) {
  return (
    <div className="summary-card__status" data-testid="summary-status">
      <div className="summary-card__status-head">
        <span className="summary-card__status-title">账号状态</span>
        <span className="summary-card__status-caption">共 {total} 个账号</span>
      </div>
      <div className="summary-status__items">
        <StatusMetric
          count={available}
          label="可用"
          tone="available"
          testId="summary-available"
        />
        <StatusMetric
          count={cooling}
          label="冷却中"
          tone="cooldown"
          testId="summary-cooldown"
        />
        <StatusMetric
          count={disabled}
          label="已禁用"
          tone="disabled"
          testId="summary-disabled"
        />
      </div>
    </div>
  );
}

/** 统计摘要卡（PRD-C1 FR4；C5 合并账号状态与总额度进度条）。 */
export function SummaryCards({
  accounts,
  quotaSummary,
}: {
  accounts: PoolAccount[];
  quotaSummary?: QuotaSummary;
}) {
  const available = accounts.filter(
    (account) => account.status === "healthy" && account.enabled,
  ).length;
  const cooling = accounts.filter((account) => account.status === "cooldown").length;
  const disabled = accounts.filter(
    (account) => account.status === "disabled" || account.enabled === false,
  ).length;

  const accountStatus = (
    <AccountStatus
      total={accounts.length}
      available={available}
      cooling={cooling}
      disabled={disabled}
    />
  );

  return (
    <div className="summary-cards" data-testid="summary-cards">
      {quotaSummary ? (
        <section className="summary-card summary-card--quota" data-testid="summary-quota">
          <div className="summary-card__quota-head">
            <div className="summary-card__quota-title">
              <div className="summary-card__num" data-testid="summary-quota-available">
                {quotaSummary.rolling_available}/{quotaSummary.queried}
              </div>
              <div>
                <div className="summary-card__label">额度可用</div>
                <div className="summary-card__quota-caption">滚动窗口可用账号</div>
              </div>
            </div>

            <div className="summary-card__quota-averages" aria-label="各窗口平均已用比例">
              {QUOTA_ROWS.map((row) => (
                <div className="summary-card__quota-average" key={row.key}>
                  <span>{row.averageLabel}</span>
                  <strong>{quotaSummary[row.averageKey]}%</strong>
                </div>
              ))}
            </div>

            {accountStatus}
          </div>

          <div className="summary-card__quota-rows">
            {QUOTA_ROWS.map((row) => {
              const percent = quotaUsagePercent(quotaSummary, row.key);
              const tone = quotaTone(percent, "ok");
              const used = quotaSummary.estimated_used_usd[row.key];
              const allocated = quotaSummary.allocated_usd[row.key];

              return (
                <div className="quota-row quota-row--summary" key={row.key}>
                  <div className="quota-row__head">
                    <span className="quota-row__label">{row.label}</span>
                    <span className="quota-row__amount">
                      <span>{`估算 $${used}`}</span>
                      <span>{`总额 $${allocated}`}</span>
                    </span>
                  </div>
                  <div
                    className="quota-row__bar quota-row__bar--summary"
                    data-testid={row.testId}
                    role="progressbar"
                    aria-label={`${row.label}已用比例`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                  >
                    <div
                      className={`quota-row__fill quota-row__fill--${tone}`}
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                  <div className="quota-row__meta">
                    <span>已用 {percent}%</span>
                    <span>账号均值 {quotaSummary[row.averageKey]}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <section className="summary-card summary-card--status-only" data-testid="summary-panel">
          {accountStatus}
        </section>
      )}
    </div>
  );
}
