import { useAccountPolling } from "../dashboard/useAccountPolling";
import { SummaryCards } from "../dashboard/SummaryCards";
import { AccountCard } from "../dashboard/AccountCard";
import { UsageCharts } from "../charts/UsageCharts";
import { ModelUsageChart } from "../charts/ModelUsageChart";
import { AccountLoadChart } from "../charts/AccountLoadChart";
import { EventTimeline } from "../charts/EventTimeline";
import { AccountControls } from "./AccountControls";
import { LogsOverviewCard } from "./LogsOverviewCard";
import { useI18n } from "../../i18n";
import { useCallback } from "react";

/**
 * Tab1：用量信息（C3 FR8；C5 额度；D1 日志升级；E2 i18n）。
 * 汇总卡（含额度总览）+ 运行概览（活跃 Key/速率/剩余时长）+ 账号卡（额度区块 + 控制按钮）
 * + 用量趋势图 + 模型分布/账号负载图 + 统一事件时间线（分页）。
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
        <h2 className="card-title">{t("chart.title.usage")}</h2>
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
        <h2 className="card-title">{t("events.title")}</h2>
        <EventTimeline />
      </section>
    </div>
  );
}
