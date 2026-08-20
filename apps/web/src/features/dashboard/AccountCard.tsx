import type { PoolAccount } from "../../types/pool";
import { StatusBadge } from "./StatusBadge";

function formatRemaining(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds <= 0) return "即将恢复";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}h ${m}m ${s}s`;
}

/** 单账号卡片（PRD-C1 FR2/FR3）。api_key 绝不应在此处出现（后端已脱敏）。 */
export function AccountCard({ account }: { account: PoolAccount }) {
  const dimmed = !account.enabled || account.status === "disabled";
  return (
    <section
      className={`account-card${dimmed ? " account-card--dimmed" : ""}`}
      data-testid="account-card"
    >
      <div className="account-card__head">
        <span className="account-card__name">{account.name}</span>
        <span className="account-card__id">{account.id}</span>
        <StatusBadge status={account.status} />
      </div>
      <div className="account-card__meta">
        {account.status === "cooldown" && (
          <div className="account-card__field">
            剩余:
            <span className="account-card__value">{formatRemaining(account.cooldown_seconds_remaining)}</span>
          </div>
        )}
        <div className="account-card__field">
          连续失败:
          <span className="account-card__value">{account.consecutive_failures}</span>
        </div>
        <div className="account-card__field">
          累计失败:
          <span className="account-card__value">{account.error_count}</span>
        </div>
      </div>
      {account.last_error && (
        <div className="account-card__error" title={account.last_error}>
          {account.last_error}
        </div>
      )}
    </section>
  );
}
