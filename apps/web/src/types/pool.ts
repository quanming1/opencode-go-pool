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

export interface SwitchEvent {
  ts: string;
  account_id: string;
  kind: string;
  reason: string | null;
  kind_label: string;
}

export interface SwitchHistoryResponse {
  events: SwitchEvent[];
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
