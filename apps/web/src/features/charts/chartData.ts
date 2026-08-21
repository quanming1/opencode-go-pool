/** 图表数据纯函数（E5）：X 轴标签格式化 / 小时级成功率 / 账号 Token 占比。
 * 与组件分离（避免 react-refresh 限制），可独立单测。
 */
import type { PerAccountUsage, StatsResponse, UsageBucket } from "../../types/pool";

/** 小时桶时间标签（≤48h HH:MM；更长 MM-DD HH:MM，与 UsageCharts 一致）。 */
export function bucketLabel(ts: string, hours: number): string {
  return hours > 48 ? `${ts.slice(5, 10)} ${ts.slice(11, 16)}` : ts.slice(11, 16);
}

/** 每桶成功率（0-100，%）：优先 success_count，旧后端回退 request_count - error_count；无请求为 null。 */
export function bucketSuccessRates(
  stats: StatsResponse,
): Array<{ ts: string; label: string; rate: number | null }> {
  return stats.buckets.map((b: UsageBucket) => {
    const total = b.request_count;
    if (total <= 0) return { ts: b.ts, label: bucketLabel(b.ts, stats.hours), rate: null };
    const ok = b.success_count ?? Math.max(0, total - (b.error_count ?? 0));
    const rate = Math.round((ok / total) * 1000) / 10;
    return { ts: b.ts, label: bucketLabel(b.ts, stats.hours), rate };
  });
}

/** 各账号 Token（prompt+completion）占比数据：过滤 tokens=0，按 token 降序。 */
export function accountTokenShare(
  stats: StatsResponse,
): Array<{ account: string; tokens: number; requests: number }> {
  return stats.per_account
    .map((a: PerAccountUsage) => ({
      account: a.account_id,
      tokens: a.prompt_tokens + a.completion_tokens,
      requests: a.request_count,
    }))
    .filter((x) => x.tokens > 0)
    .sort((a, b) => b.tokens - a.tokens);
}
