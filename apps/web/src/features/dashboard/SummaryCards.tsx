import type { PoolAccount } from "../../types/pool";

/** 统计摘要卡（PRD-C1 FR4）：可用 / 冷却中 / 已禁用。 */
export function SummaryCards({ accounts }: { accounts: PoolAccount[] }) {
  const started = accounts.filter(
    (a) => a.status === "healthy" && a.enabled,
  ).length;
  const cooling = accounts.filter((a) => a.status === "cooldown").length;
  const disabled = accounts.filter(
    (a) => a.status === "disabled" || (a.enabled === false),
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
    </div>
  );
}
