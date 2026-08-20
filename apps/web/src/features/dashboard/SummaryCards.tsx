import type { PoolAccount, QuotaSummary } from "../../types/pool";
import { quotaTone } from "./quotaFormat";
import { useI18n, type MessageKey } from "../../i18n";
const QUOTA_ROWS: {
  key: "rolling" | "weekly" | "monthly";
  labelKey: MessageKey;
  averageKey: "rolling_avg_percent" | "weekly_avg_percent" | "monthly_avg_percent";
  averageLabelKey: MessageKey;
  testId: string;
}[] = [
  {
    key: "rolling",
    labelKey: "quota.rolling",
    averageKey: "rolling_avg_percent",
    averageLabelKey: "quota.avg.rolling",
    testId: "summary-quota-bar-rolling",
  },
  {
    key: "weekly",
    labelKey: "quota.weekly",
    averageKey: "weekly_avg_percent",
    averageLabelKey: "quota.avg.weekly",
    testId: "summary-quota-bar-weekly",
  },
  {
    key: "monthly",
    labelKey: "quota.monthly",
    averageKey: "monthly_avg_percent",
    averageLabelKey: "quota.avg.monthly",
    testId: "summary-quota-bar-monthly",
  },
];

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
  const { t } = useI18n();
  return (
    <div className="summary-card__status" data-testid="summary-status">
      <div className="summary-card__status-head">
        <span className="summary-card__status-title">{t("summary.title")}</span>
        <span className="summary-card__status-caption">
          {t("summary.total", { n: total })}
        </span>
      </div>
      <div className="summary-status__items">
        <StatusMetric count={available} label={t("summary.available")} tone="available" testId="summary-available" />
        <StatusMetric count={cooling} label={t("summary.cooldown")} tone="cooldown" testId="summary-cooldown" />
        <StatusMetric count={disabled} label={t("summary.disabled")} tone="disabled" testId="summary-disabled" />
      </div>
    </div>
  );
}

/** 统计摘要卡（PRD-C1 FR4；C5 合并账号状态与总额度进度条；E2 i18n）。 */
export function SummaryCards({
  accounts,
  quotaSummary,
}: {
  accounts: PoolAccount[];
  quotaSummary?: QuotaSummary;
}) {
  const { t } = useI18n();
  const available = accounts.filter(
    (account) => account.status === "healthy" && account.enabled,
  ).length;
  const cooling = accounts.filter((account) => account.status === "cooldown").length;
  const disabled = accounts.filter(
    (account) => account.status === "disabled" || account.enabled === false,
  ).length;

  const accountStatus = (
    <AccountStatus total={accounts.length} available={available} cooling={cooling} disabled={disabled} />
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
                <div className="summary-card__label">{t("quota.available")}</div>
                <div className="summary-card__quota-caption">{t("quota.caption")}</div>
              </div>
            </div>

            <div className="summary-card__quota-averages" aria-label="average usage per window">
              {QUOTA_ROWS.map((row) => (
                <div className="summary-card__quota-average" key={row.key}>
                  <span>{t(row.averageLabelKey)}</span>
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
                    <span className="quota-row__label">{t(row.labelKey)}</span>
                    <span className="quota-row__amount">
                      <span>{t("quota.est", { v: used })}</span>
                      <span>{t("quota.total", { v: allocated })}</span>
                    </span>
                  </div>
                  <div
                    className="quota-row__bar quota-row__bar--summary"
                    data-testid={row.testId}
                    role="progressbar"
                    aria-label={`${t(row.labelKey)} usage`}
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
                    <span>{t("quota.used", { p: percent })}</span>
                    <span>{`${t(row.averageLabelKey)} ${quotaSummary[row.averageKey]}%`}</span>
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
