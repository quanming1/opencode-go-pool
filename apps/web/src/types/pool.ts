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
}

export interface UsageBucket {
  ts: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
}

export interface PerAccountUsage {
  account_id: string;
  request_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  error_count: number;
}

export interface StatsResponse {
  hours: number;
  totals: UsageTotals;
  per_account: PerAccountUsage[];
  buckets: UsageBucket[];
}

export interface EventItem {
  type: string;
  data: Record<string, unknown>;
  meta: Record<string, unknown>;
  time: string;
}

export interface EventsResponse {
  events: EventItem[];
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
