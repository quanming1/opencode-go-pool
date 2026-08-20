/** 后端 API 客户端（C1：/api/accounts；C2 追加 /api/stats 等）。 */

import type { AccountsResponse, PoolAccount } from "../types/pool";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`请求失败: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function fetchAccounts(): Promise<PoolAccount[]> {
  const data = await fetchJson<AccountsResponse>("/api/accounts");
  return data.accounts;
}

export type { PoolAccount } from "../types/pool";
