import { useAccountPolling } from "../dashboard/useAccountPolling";
import { SummaryCards } from "../dashboard/SummaryCards";
import { AccountCard } from "../dashboard/AccountCard";
import { UsageCharts } from "../charts/UsageCharts";
import { EventTimeline } from "../charts/EventTimeline";
import { AccountControls } from "./AccountControls";
import { useCallback } from "react";

/**
 * Tab1：用量信息（C3 FR8；C5 额度）。
 * 汇总卡（含额度总览）+ 账号卡（额度区块 + 控制按钮）+ 用量趋势图 + 统一事件时间线。
 * 控制操作后 forceTick 立即拉取最新数据（不等下一轮询）；
 * 「刷新额度」强制绕过服务端缓存重新查询上游。
 */
export function UsagePanel() {
  const {
    accounts,
    stats,
    events,
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
          无法刷新大盘数据: {error}（显示上次数据）
        </p>
      )}

      <div className="account-list">
        {loading && accounts.length === 0 ? (
          <p className="dashboard-empty">加载中…</p>
        ) : accounts.length === 0 ? (
          <p className="dashboard-empty">暂无账号。请配置 config/accounts.yaml 后重启后端。</p>
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
          <h2 className="card-title">额度（OpenCode Go 官方接口）</h2>
          <button
            className="btn"
            type="button"
            onClick={() => void onRefreshQuota()}
            disabled={quotaBusy}
            data-testid="quota-refresh"
          >
            {quotaBusy ? "刷新中…" : "刷新额度"}
          </button>
        </div>
        {quotaError && (
          <p className="dashboard-error" role="alert">
            刷新额度失败: {quotaError}（显示上次数据）
          </p>
        )}
        <p className="quota-note">
          滚动窗口 5 小时 $12 / 每周 $30 / 每月 $60（每账号）。
          {quota?.fetched_at
            ? ` 取数时间 ${new Date(quota.fetched_at).toLocaleString("zh-CN", { hour12: false })}${quota.cached ? "（缓存）" : ""}`
            : ""}
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">用量趋势（近24h）</h2>
        {stats && stats.buckets.length > 0 ? (
          <UsageCharts stats={stats} />
        ) : (
          <p className="dashboard-empty">暂无用量数据</p>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">事件时间线</h2>
        <EventTimeline events={events} />
      </section>
    </div>
  );
}