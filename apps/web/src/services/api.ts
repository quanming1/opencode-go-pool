/** 后端 API 客户端（C1：/api/accounts；C2 追加 /api/stats 等）。 */

import type {
  AccountsResponse,
  CreatedGatewayKey,
  GatewayKey,
  PoolAccount,
  StatsResponse,
  SwitchEvent,
  SwitchHistoryResponse,
} from "../types/pool";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`请求失败: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`请求失败: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function fetchAccounts(): Promise<PoolAccount[]> {
  const data = await fetchJson<AccountsResponse>("/api/accounts");
  return data.accounts;
}

export async function fetchStats(hours = 24): Promise<StatsResponse> {
  return fetchJson<StatsResponse>(`/api/stats?hours=${hours}`);
}

export async function fetchSwitchHistory(limit = 50): Promise<SwitchEvent[]> {
  const data = await fetchJson<SwitchHistoryResponse>(
    `/api/switch-history?limit=${limit}`,
  );
  return data.events;
}

// ---- C3：账号控制 ----

export async function clearAccount(id: string): Promise<{ ok: boolean }> {
  return postJson(`/api/accounts/${encodeURIComponent(id)}/clear`);
}

export async function disableAccount(id: string): Promise<{ ok: boolean }> {
  return postJson(`/api/accounts/${encodeURIComponent(id)}/disable`);
}

export async function enableAccount(id: string): Promise<{ ok: boolean }> {
  return postJson(`/api/accounts/${encodeURIComponent(id)}/enable`);
}

// ---- C3：网关 key 管理 ----

/**
 * 管理凭证：生成 key 后存 localStorage，后续 keys 管理请求自动携带。
 * 场景：生成第一个 key 后 /api/keys 激活鉴权，不带凭证会 401 自锁。
 * 本地单管理员部署语义下可接受（这是管理台自身的凭证，非分发给客户端的 key）。
 */
const ADMIN_KEY_STORAGE = "ocp.gateway.admin.key";

export function rememberAdminKey(key: string): void {
  localStorage.setItem(ADMIN_KEY_STORAGE, key);
}

function adminAuthHeaders(): Record<string, string> {
  const k = localStorage.getItem(ADMIN_KEY_STORAGE);
  return k ? { Authorization: `Bearer ${k}` } : {};
}

export async function fetchGatewayKeys(): Promise<GatewayKey[]> {
  const res = await fetch(`${BASE_URL}/api/keys`, { headers: adminAuthHeaders() });
  if (!res.ok) throw new Error(`请求失败: ${res.status}`);
  return ((await res.json()) as { keys: GatewayKey[] }).keys;
}

export async function createGatewayKey(label: string): Promise<CreatedGatewayKey> {
  const res = await fetch(`${BASE_URL}/api/keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...adminAuthHeaders() },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) {
    throw new Error(`创建失败: ${res.status}`);
  }
  const created = (await res.json()) as CreatedGatewayKey;
  rememberAdminKey(created.key);
  return created;
}

export async function revokeGatewayKey(id: number): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE_URL}/api/keys/${id}`, {
    method: "DELETE",
    headers: adminAuthHeaders(),
  });
  if (!res.ok) throw new Error(`请求失败: ${res.status}`);
  return (await res.json()) as { ok: boolean };
}

export type { PoolAccount, StatsResponse, SwitchEvent } from "../types/pool";
