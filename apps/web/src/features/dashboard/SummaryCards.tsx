import type { PoolAccount, QuotaSummary } from "../../types/pool";

/** 统计摘要卡（PRD-C1 FR4；C5 增加每账号总额度汇总）。 */
export function SummaryCards({
  accounts,
  quotaSummary,
}: {
  accounts: PoolAccount[];
  quotaSummary?: QuotaSummary;
}) {
  const started = accounts.filter(
    (a) => a.status === "healthy" && a.enabled,
  ).length;
  const cooling = accounts.filter((a) => a.status === "cooldown").length;
  const disabled = accounts.filter(
    (a) => a.status === "disabled" || a.enabled === false,
  ).length;

  return (
    <div className="summary-cards" data-testid="summary-cards">
      <div className="summary-card">
        <div className="summary-card__num" data-testid="summary-available">{started}</div>
        <div className="summary-card__label">可用</div>
      </div>
      <div className="summary-card">
        <div className="summary-card__num" data-testid="summary-cooldown">{cooling}</div>
        <div className="summary-card__label">冷却中</div>
      </div>
      <div className="summary-card">
        <div className="summary-card__num" data-testid="summary-disabled">{disabled}</div>
        <div className="summary-card__label">已禁用</div>
      </div>
      {quotaSummary && (
        <div className="summary-card summary-card--quota" data-testid="summary-quota">
          <div className="summary-card__num" data-testid="summary-quota-available">
            {quotaSummary.rolling_available}/{quotaSummary.queried}
          </div>
          <div className="summary-card__label">额度可用</div>
          <div className="summary-card__quota-rows">
            <div className="quota-mini">
              <span>滚动</span>
              <span>{`估算 $${quotaSummary.estimated_used_usd.rolling} / 总额 $${quotaSummary.allocated_usd.rolling}`}</span>
            </div>
            <div className="quota-mini">
              <span>每周</span>
              <span>{`估算 $${quotaSummary.estimated_used_usd.weekly} / 总额 $${quotaSummary.allocated_usd.weekly}`}</span>
            </div>
            <div className="quota-mini">
              <span>每月</span>
              <span>{`估算 $${quotaSummary.estimated_used_usd.monthly} / 总额 $${quotaSummary.allocated_usd.monthly}`}</span>
            </div>
          </div>
          <div className="summary-card__quota-rows">
            <div className="quota-mini">
              <span>滚动均值</span>
              <span>{quotaSummary.rolling_avg_percent}%</span>
            </div>
            <div className="quota-mini">
              <span>每周均值</span>
              <span>{quotaSummary.weekly_avg_percent}%</span>
            </div>
            <div className="quota-mini">
              <span>每月均值</span>
              <span>{quotaSummary.monthly_avg_percent}%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
