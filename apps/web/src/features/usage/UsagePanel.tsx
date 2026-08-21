import { useAccountPolling, type StatsHours } from "../dashboard/useAccountPolling";
import { SummaryCards } from "../dashboard/SummaryCards";
import { AccountCard } from "../dashboard/AccountCard";
import { UsageCharts } from "../charts/UsageCharts";
import { ModelUsageChart } from "../charts/ModelUsageChart";
import { AccountLoadChart } from "../charts/AccountLoadChart";
import { ProtocolChart } from "../charts/ProtocolChart";
import { ErrorTypeChart } from "../charts/ErrorTypeChart";
import { SuccessRateTrendChart } from "../charts/SuccessRateTrendChart";
import { AccountTokenShareChart } from "../charts/AccountTokenShareChart";
import { accountTokenShare } from "../charts/chartData";
import { EventTimeline } from "../charts/EventTimeline";
import { AccountControls } from "./AccountControls";
import { LogsOverviewCard } from "./LogsOverviewCard";
import { StatsSummaryCard } from "./StatsSummaryCard";
import { useI18n, type MessageKey } from "../../i18n";
import { useCallback } from "react";

/** E5：统计周期选项（小时窗口，后端 /api/stats?hours= 已支持 1..168）。 */
const PERIODS: Array<{ hours: StatsHours; label: MessageKey }> = [
  { hours: 24, label: "chart.period.24h" },
  { hours: 72, label: "chart.period.72h" },
  { hours: 168, label: "chart.period.168h" },
];

/**
 * Tab1：用量信息（C3 FR8；C5 额度；D1 日志升级；E2 i18n；E4 运行汇总；E5 周期切换 + 构成分析）。
 * 汇总卡（含额度总览）+ 运行概览（活跃 Key/速率/剩余时长）+ 账号卡（额度区块 + 控制按钮）
 * + 运行汇总 + 用量趋势图（周期可切换、Token 构成堆叠）+ 模型/账号负载图
 * + 构成分析栅格（成功率趋势/账号 Token 占比/协议分布/错误类型）+ 统一事件时间线（分页）。
 */
export function UsagePanel() {
  const { t } = useI18n();
  const {
    accounts,
    stats,
    overview,
    overviewError,
    quota,
    quotaBusy,
    error,
    quotaError,
    loading,
    statsHours,
    setStatsHours,
    refresh,
    forceRefreshQuota,
  } = useAccountPolling();
  const onControlChanged = useCallback(() => void refresh(), [refresh]);

  const onRefreshQuota = useCallback(async () => {
    await forceRefreshQuota();
  }, [forceRefreshQuota]);

  const quotaByAccount = new Map(
    (quota?.accounts ?? []).map((a) => [a.account_id, a]),
  );

  return (
    <div className="dashboard">
      <SummaryCards accounts={accounts} quotaSummary={quota?.summary} />

      {error && (
        <p className="dashboard-error" role="alert">
          {t("common.refreshFailed")}: {error}{t("common.showLastData")}
        </p>
      )}

      <LogsOverviewCard overview={overview} error={overviewError} />

      <div className="account-list">
        {loading && accounts.length === 0 ? (
          <p className="dashboard-empty">{t("common.loading")}</p>
        ) : accounts.length === 0 ? (
          <p className="dashboard-empty">{t("common.noAccounts")}</p>
        ) : (
          accounts.map((a) => (
            <AccountCard key={a.id} account={a} quota={quotaByAccount.get(a.id)}>
              <AccountControls account={a} onChanged={onControlChanged} />
            </AccountCard>
          ))
        )}
      </div>

      <section className="card">
        <div className="card-head-row">
          <h2 className="card-title">{t("quota.sectionTitle")}</h2>
          <button
            className="btn"
            type="button"
            onClick={() => void onRefreshQuota()}
            disabled={quotaBusy}
            data-testid="quota-refresh"
          >
            {quotaBusy ? t("quota.refreshing") : t("quota.refresh")}
          </button>
        </div>
        {quotaError && (
          <p className="dashboard-error" role="alert">
            {t("quota.fetchFailed")}: {quotaError}{t("common.showLastData")}
          </p>
        )}
        <p className="quota-note">
          {t("quota.limitsHelp")}
          {quota?.fetched_at
            ? ` ${t("quota.fetchedAt", { ts: new Date(quota.fetched_at).toLocaleString(undefined, { hour12: false }) })}${quota.cached ? t("quota.cached") : ""}`
            : ""}
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">{t("stats.title")}</h2>
        {stats ? (
          <StatsSummaryCard stats={stats} />
        ) : (
          <p className="dashboard-empty">{t("common.loading")}</p>
        )}
      </section>

      <section className="card">
        <div className="card-head-row">
          <h2 className="card-title">{t("chart.title.usage")}</h2>
          <div className="period-switch" role="group" aria-label={t("stats.hours")}>
            {PERIODS.map((p) => (
              <button
                key={p.hours}
                type="button"
                className="btn"
                disabled={statsHours === p.hours}
                onClick={() => setStatsHours(p.hours)}
                data-testid={`stats-hours-${p.hours}`}
              >
                {t(p.label)}
              </button>
            ))}
          </div>
        </div>
        {stats && stats.buckets.length > 0 ? (
          <UsageCharts stats={stats} />
        ) : (
          <p className="dashboard-empty">{t("chart.empty.usage")}</p>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">{t("chart.title.models")}</h2>
        {stats && stats.per_account_models.length > 0 ? (
          <ModelUsageChart stats={stats} />
        ) : (
          <p className="dashboard-empty">{t("chart.empty.models")}</p>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">{t("chart.title.accounts")}</h2>
        {stats && stats.per_account.length > 0 ? (
          <AccountLoadChart stats={stats} />
        ) : (
          <p className="dashboard-empty">{t("chart.empty.accounts")}</p>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">{t("chart.title.mini")}</h2>
        <div className="mini-chart-grid">
          <div className="mini-chart">
            <h3 className="mini-chart__title">{t("chart.title.successRate")}</h3>
            {stats && stats.buckets.length > 0 ? (
              <SuccessRateTrendChart stats={stats} />
            ) : (
              <p className="dashboard-empty">{t("chart.empty.usage")}</p>
            )}
          </div>
          <div className="mini-chart">
            <h3 className="mini-chart__title">{t("chart.title.tokenShare")}</h3>
            {stats && accountTokenShare(stats).length > 0 ? (
              <AccountTokenShareChart stats={stats} />
            ) : (
              <p className="dashboard-empty">{t("chart.empty.accounts")}</p>
            )}
          </div>
          <div className="mini-chart">
            <h3 className="mini-chart__title">{t("chart.title.protocol")}</h3>
            {stats && stats.summary && stats.summary.protocol.length > 0 ? (
              <ProtocolChart stats={stats} />
            ) : (
              <p className="dashboard-empty">{t("chart.empty.protocol")}</p>
            )}
          </div>
          <div className="mini-chart">
            <h3 className="mini-chart__title">{t("chart.title.errorTypes")}</h3>
            {stats && stats.error_types && stats.error_types.length > 0 ? (
              <ErrorTypeChart stats={stats} />
            ) : (
              <p className="dashboard-empty">{t("chart.empty.errorTypes")}</p>
            )}
          </div>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">{t("events.title")}</h2>
        <EventTimeline />
      </section>
    </div>
  );
}
