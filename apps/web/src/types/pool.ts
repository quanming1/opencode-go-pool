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
