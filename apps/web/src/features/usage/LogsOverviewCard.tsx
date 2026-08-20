import type { LogsOverview } from "../../types/pool";
import { useI18n } from "../../i18n";

function fmtNumber(n: number | undefined | null): string {
  return n === undefined || n === null ? "-" : String(n);
}

/** 日志概览卡（D1 FR3/FR4；E2 i18n）：当前活跃 Key + 请求速率 + 剩余使用时长推测。 */
export function LogsOverviewCard({
  overview,
  error,
}: {
  overview: LogsOverview | null;
  error: string | null;
}) {
  const { t } = useI18n();
  const active = overview?.current_active ?? null;
  const rem = overview?.usage_remaining ?? null;
  const rate = overview?.rate;

  return (
    <section className="card">
      <div className="card-head-row">
        <h2 className="card-title">{t("logs.title")}</h2>
        {error && <span className="quota-note">{t("common.showLastData")}</span>}
      </div>
      <div className="overview-grid">
        <div className="overview-cell" data-testid="overview-active">
          <span className="overview-cell__label">{t("logs.activeKey")}</span>
          <strong className="overview-cell__value">
            {active ? (
              <>
                {active.account_id}
                <span className="overview-cell__hint">
                  （{new Date(active.last_success_at).toLocaleString(undefined, { hour12: false })}）
                </span>
              </>
            ) : (
              "-"
            )}
          </strong>
        </div>
        <div className="overview-cell" data-testid="overview-rate">
          <span className="overview-cell__label">{t("logs.rate")}</span>
          <strong className="overview-cell__value">
            {t("logs.rateValue", {
              rpm: fmtNumber(rate?.requests_per_minute),
              tph: fmtNumber(rate?.tokens_per_hour),
            })}
          </strong>
        </div>
        <div className="overview-cell" data-testid="overview-remaining">
          <span className="overview-cell__label">{t("logs.remaining")}</span>
          <strong className="overview-cell__value">
            {rem
              ? t("logs.remainingValue", {
                  h: fmtNumber(rem.estimated_hours_left),
                  n: fmtNumber(rem.estimated_requests_left),
                })
              : t("logs.noData")}
          </strong>
          {rem && <span className="overview-cell__hint">{t("logs.note")}</span>}
        </div>
      </div>
    </section>
  );
}
