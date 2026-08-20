import type { ReactNode } from "react";
import type { AccountQuota, PoolAccount, QuotaWindow } from "../../types/pool";
import { StatusBadge } from "./StatusBadge";
import { quotaTone, resetsInText } from "./quotaFormat";
import { useI18n } from "../../i18n";

function QuotaWindowRow({ label, win }: { label: string; win: QuotaWindow }) {
  const { t } = useI18n();
  const tone = quotaTone(win.percent, win.status);
  const limited = win.status === "rate-limited";
  return (
    <div className="quota-row">
      <span className="quota-row__label">{label}</span>
      <div className="quota-row__bar">
        <div
          className={`quota-row__fill quota-row__fill--${tone}`}
          style={{ width: `${Math.min(100, Math.max(0, win.percent))}%` }}
        />
      </div>
      <span className={`quota-row__percent quota-row__percent--${tone}`}>
        {limited ? t("quota.limited") : t("quota.used", { p: win.percent })}
      </span>
      <span className="quota-row__reset">
        {t("quota.resetsIn", { x: resetsInText(win.resets_in_seconds) })}
      </span>
    </div>
  );
}

/** 单账号卡片（PRD-C1 FR2/FR3；C3 控制按钮插槽；C5 额度区块；E2 i18n）。api_key 绝不应在此处出现（后端已脱敏）。 */
export function AccountCard({
  account,
  quota,
  children,
}: {
  account: PoolAccount;
  quota?: AccountQuota;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  const dimmed = !account.enabled || account.status === "disabled";
  const hasQuota = quota !== undefined && quota.quota !== null;

  const WINDOW_LABELS: { key: keyof NonNullable<AccountQuota["quota"]>; label: string }[] = [
    { key: "rolling", label: t("quota.rolling") },
    { key: "weekly", label: t("quota.weekly") },
    { key: "monthly", label: t("quota.monthly") },
  ];

  function formatRemaining(seconds: number | null): string {
    if (seconds === null) return "-";
    if (seconds <= 0) return t("account.restoring");
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h}h ${m}m ${s}s`;
  }

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
            {t("account.remaining")}:
            <span className="account-card__value">{formatRemaining(account.cooldown_seconds_remaining)}</span>
          </div>
        )}
        <div className="account-card__field">
          {t("account.consecFailures")}:
          <span className="account-card__value">{account.consecutive_failures}</span>
        </div>
        <div className="account-card__field">
          {t("account.totalFailures")}:
          <span className="account-card__value">{account.error_count}</span>
        </div>
      </div>
      {(quota !== undefined || children !== undefined) && (
        <div className="account-card__body">
          {quota !== undefined && (
            <div className="quota-block" data-testid="quota-block">
              {hasQuota ? (
                WINDOW_LABELS.map(({ key, label }) => (
                  <QuotaWindowRow key={key} label={label} win={quota.quota![key]} />
                ))
              ) : (
                <div className="quota-block__unknown">
                  {t("quota.unknown")}{quota.error ? `（${quota.error}）` : ""}
                </div>
              )}
            </div>
          )}
          {children && <div className="account-card__controls">{children}</div>}
        </div>
      )}
      {account.last_error && (
        <div className="account-card__error" title={account.last_error}>
          {account.last_error}
        </div>
      )}
    </section>
  );
}
