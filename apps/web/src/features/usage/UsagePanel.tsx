import { useAccountPolling } from "../dashboard/useAccountPolling";
import { SummaryCards } from "../dashboard/SummaryCards";
import { AccountCard } from "../dashboard/AccountCard";
import { UsageCharts } from "../charts/UsageCharts";
import { EventTimeline } from "../charts/EventTimeline";
import { AccountControls } from "./AccountControls";
import { useCallback } from "react";

/**
 * Tab1：用量信息（C3 FR8）。
 * 汇总卡 + 账号卡（含控制按钮）+ 用量趋势图 + 统一事件时间线。
 * 控制操作后 forceTick 立即拉取最新数据（不等下一轮询）。
 */
export function UsagePanel() {
  const { accounts, stats, events, error, loading, refresh } = useAccountPolling();
  const onControlChanged = useCallback(() => void refresh(), [refresh]);

  return (
    <div className="dashboard">
      <SummaryCards accounts={accounts} />

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
            <AccountCard key={a.id} account={a}>
              <AccountControls account={a} onChanged={onControlChanged} />
            </AccountCard>
          ))
        )}
      </div>

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
