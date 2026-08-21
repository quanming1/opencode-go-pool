/** 账号池类型定义（对应后端 GET /api/accounts）。 */

export type AccountStatus = "healthy" | "cooldown" | "disabled";

export interface PoolAccount {
  id: string;
  name: string;
  status: AccountStatus;
  cooldown_until: string | null;
  cooldown_seconds_remaining: number | null;
  last_error: string | null;
  error_count: number;
  consecutive_failures: number;
  enabled: boolean;
}

export interface AccountsResponse {
  accounts: PoolAccount[];
}

export interface UsageTotals {
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
  /** E4：成功响应数 / 上游尝试级成功率（旧后端/旧库可能缺失，前端按 0 兜底）。 */
  success_count?: number;
  success_rate?: number;
}

export interface UsageBucket {
  ts: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
  /** E4：成功响应数（可选，兼容旧数据）。 */
  success_count?: number;
}

export interface PerAccountUsage {
  account_id: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
  /** E4：成功响应数（可选，兼容旧数据）。 */
  success_count?: number;
}

/** D1：按账号 × 模型聚合（某 Key 收到多少次请求、分别什么模型）。 */
export interface PerAccountModelUsage {
  account_id: string;
  model: string | null;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
  /** E4：成功响应数（可选，兼容旧数据）。 */
  success_count?: number;
}

/** E4：错误类型分布（usage_events 的 error_type 分组计数）。 */
export interface ErrorTypeCount {
  type: string;
  count: number;
}

/** E4：request 事件耗时汇总（近 N 条事件，p95 样本 <2 时为 null）。 */
export interface DurationStats {
  avg: number | null;
  p95: number | null;
  max: number | null;
}

/** E4：协议分布（responses / chat_completions 等）。 */
export interface ProtocolCount {
  name: string;
  count: number;
}

/** E4：近期状态类事件计数（键与后端 EventType 一致）。 */
export interface EventCounts {
  key_switch: number;
  key_cooldown_started: number;
  key_disabled: number;
  all_keys_unavailable: number;
  all_keys_invalid: number;
}

/** E4：events 派生聚合（耗时/协议分布/事件计数；旧后端可能缺失）。 */
export interface StatsSummary {
  window: number;
  duration_ms: DurationStats;
  protocol: ProtocolCount[];
  event_counts: EventCounts;
}

export interface StatsResponse {
  hours: number;
  totals: UsageTotals;
  per_account: PerAccountUsage[];
  per_account_models: PerAccountModelUsage[];
  buckets: UsageBucket[];
  /** E4：错误类型分布（可选，兼容旧后端）。 */
  error_types?: ErrorTypeCount[];
  /** E4：事件派生汇总（可选，兼容旧后端）。 */
  summary?: StatsSummary;
  /** G8：统计模式（fast=内存聚合口径，normal=持久化口径；可选，兼容旧后端）。 */
  mode?: "fast" | "normal";
}

export interface EventItem {
  type: string;
  data: Record<string, unknown>;
  meta: Record<string, unknown>;
  time: string;
}

export interface EventsResponse {
  events: EventItem[];
  offset: number;
  has_more: boolean;
}

// ---- D1：日志概览 ----

/** 当前正在接受外部请求的 Key（最近成功请求的账号）。 */
export interface CurrentActiveKey {
  account_id: string;
  last_success_at: string;
}

/** 最近窗口请求/token 速率。 */
export interface UsageRate {
  minutes: number;
  requests_per_minute: number;
  tokens_per_hour: number;
}

/** 剩余使用时长推测（估算口径，非账单）。 */
export interface UsageRemaining {
  estimated_requests_left: number;
  estimated_hours_left: number;
  basis: string;
  note: string;
}

export interface LogsOverview {
  current_active: CurrentActiveKey | null;
  rate: UsageRate;
  usage_remaining: UsageRemaining | null;
}

// ---- C5：额度 ----

/** 单窗口额度（rolling/weekly/monthly）。 */
export interface QuotaWindow {
  status: string;
  percent: number;
  resets_at: string | null;
  resets_in_seconds: number | null;
}

export interface AccountQuota {
  account_id: string;
  quota: { rolling: QuotaWindow; weekly: QuotaWindow; monthly: QuotaWindow } | null;
  error: string | null;
}

export interface QuotaSummary {
  total_accounts: number;
  queried: number;
  ok_accounts: number;
  rolling_available: number;
  rolling_avg_percent: number;
  weekly_avg_percent: number;
  monthly_avg_percent: number;
  allocated_usd: { rolling: number; weekly: number; monthly: number };
  estimated_used_usd: { rolling: number; weekly: number; monthly: number };
}

export interface QuotaResponse {
  accounts: AccountQuota[];
  summary: QuotaSummary;
  fetched_at: string;
  cached: boolean;
}

export interface GatewayKey {
  id: number;
  label: string;
  created_at: string;
  revoked_at: string | null;
}

export interface CreatedGatewayKey {
  id: number;
  label: string;
  key: string;
  created_at: string;
}
