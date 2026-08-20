import { useAccountPolling } from "./useAccountPolling";
import { SummaryCards } from "./SummaryCards";
import { AccountCard } from "./AccountCard";
import { UsageCharts } from "../charts/UsageCharts";
import { SwitchTimeline } from "../charts/SwitchTimeline";

/**
 * 账号状态大盘（C1 + C2 容器）：
 * 轮询 accounts / stats / switch-history → 统计摘要 + 账号卡片 + 用量趋势图 + 轮换时间线。
 */
export function Dashboard() {
  const { accounts, stats, switchEvents, error, loading } = useAccountPolling();

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
          accounts.map((a) => <AccountCard key={a.id} account={a} />)
        )}
      </div>

      <section className="card">
        <h2 className="card-title">用量趋势（近24h）</h2>
        {stats ? <UsageCharts stats={stats} /> : <p className="dashboard-empty">暂无用量数据</p>}
      </section>

      <section className="card">
        <h2 className="card-title">轮换事件</h2>
        <SwitchTimeline events={switchEvents} />
      </section>
    </div>
  );
}
