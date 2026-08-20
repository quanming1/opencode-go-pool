import { useAccountPolling } from "./useAccountPolling";
import { SummaryCards } from "./SummaryCards";
import { AccountCard } from "./AccountCard";

/**
 * 账号状态大盘（C1 容器）：
 * 轮询 /api/accounts → 统计摘要 + 账号卡片列表。
 * 空态 / 加载 / 错误态（PRD-C1 FR5 / AC2 / AC4）。
 */
export function Dashboard() {
  const { accounts, error, loading } = useAccountPolling();

  return (
    <div className="dashboard">
      <SummaryCards accounts={accounts} />

      {error && (
        <p className="dashboard-error" role="alert">
          无法刷新账号状态: {error}（显示上次数据）
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
    </div>
  );
}
