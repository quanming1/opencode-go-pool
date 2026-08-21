import { useI18n } from "../../i18n";
import type { StatsResponse } from "../../types/pool";

/** 统计指标项：label + 值（用于运行汇总条）。 */
function StatItem({ label, value, testid }: { label: string; value: string; testid?: string }) {
  return (
    <div className="stat-item" data-testid={testid}>
      <span className="stat-item__label">{label}</span>
      <span className="stat-item__value">{value}</span>
    </div>
  );
}

/**
 * 运行汇总条（E4 FR6）：总请求 / 成功率 / 总 Token / 平均耗时 / 活跃模型 / 活跃账号。
 * 数据来自 stats.totals 与 stats.summary（新字段可选，旧后端/旧库自动兜底）。
 */
export function StatsSummaryCard({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const totals = stats.totals;
  const totalReq = totals.request_count;
  // 后端 success_rate 为 0-1 比例；此处统一转为百分比。
  // 旧后端无 success 数据且已有请求时，成功率未知 → 显示占位而非误导的 0%。
  const rate: number | null =
    totals.success_rate !== undefined
      ? totals.success_rate * 100
      : totalReq === 0
        ? 100
        : null;
  const avgMs = stats.summary?.duration_ms?.avg ?? null;
  const activeModels = new Set(
    stats.per_account_models
      .map((m) => m.model)
      .filter((m): m is string => Boolean(m)),
  ).size;
  const activeAccounts = stats.per_account.length;

  return (
    <div className="stats-summary" data-testid="stats-summary">
      {stats.mode === "fast" && (
        <div className="stats-fast-mode" data-testid="stats-fast-mode" title={t("stats.fastMode")}>
          FAST
        </div>
      )}
      <StatItem label={t("stats.requests")} value={totalReq.toLocaleString()} testid="summary-requests" />
      <StatItem
        label={t("stats.successRate")}
        value={rate === null ? t("common.notAvailable") : t("stats.percent", { value: rate.toFixed(1) })}
        testid="summary-success-rate"
      />
      <StatItem
        label={t("stats.totalTokens")}
        value={(totals.prompt_tokens + totals.completion_tokens).toLocaleString()}
        testid="summary-tokens"
      />
      <StatItem
        label={t("stats.avgDuration")}
        value={avgMs === null ? t("common.notAvailable") : t("stats.ms", { value: avgMs.toLocaleString() })}
        testid="summary-avg-duration"
      />
      <StatItem
        label={t("stats.activeModels")}
        value={activeModels.toLocaleString()}
        testid="summary-active-models"
      />
      <StatItem
        label={t("stats.activeAccounts")}
        value={activeAccounts.toLocaleString()}
        testid="summary-active-accounts"
      />
    </div>
  );
}
