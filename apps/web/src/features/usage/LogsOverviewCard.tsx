import type { LogsOverview } from "../../types/pool";

function fmtNumber(n: number | undefined | null): string {
  return n === undefined || n === null ? "-" : String(n);
}

/** 日志概览卡（D1 FR3/FR4）：当前活跃 Key + 请求速率 + 剩余使用时长推测。 */
export function LogsOverviewCard({
  overview,
  error,
}: {
  overview: LogsOverview | null;
  error: string | null;
}) {
  const active = overview?.current_active ?? null;
  const rem = overview?.usage_remaining ?? null;
  const rate = overview?.rate;

  return (
    <section className="card">
      <div className="card-head-row">
        <h2 className="card-title">运行概览</h2>
        {error && <span className="quota-note">({error}，显示上次数据)</span>}
      </div>
      <div className="overview-grid">
        <div className="overview-cell" data-testid="overview-active">
          <span className="overview-cell__label">当前活跃 Key</span>
          <strong className="overview-cell__value">
            {active ? (
              <>
                {active.account_id}
                <span className="overview-cell__hint">
                  （{new Date(active.last_success_at).toLocaleString("zh-CN", { hour12: false })}）
                </span>
              </>
            ) : (
              "-"
            )}
          </strong>
        </div>
        <div className="overview-cell" data-testid="overview-rate">
          <span className="overview-cell__label">请求速率（近60分钟）</span>
          <strong className="overview-cell__value">
            {fmtNumber(rate?.requests_per_minute)} 次/分 · {fmtNumber(rate?.tokens_per_hour)} token/时
          </strong>
        </div>
        <div className="overview-cell" data-testid="overview-remaining">
          <span className="overview-cell__label">剩余可用（估算）</span>
          <strong className="overview-cell__value">
            {rem
              ? `约 ${fmtNumber(rem.estimated_hours_left)} 小时（剩 ${fmtNumber(rem.estimated_requests_left)} 次请求）`
              : "数据不足"}
          </strong>
          {rem && <span className="overview-cell__hint">{rem.note}</span>}
        </div>
      </div>
    </section>
  );
}
