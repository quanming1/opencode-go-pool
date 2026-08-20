import { useCallback, useEffect, useState } from "react";
import {
  fetchAccounts,
  fetchEvents,
  fetchQuota,
  fetchStats,
} from "../../services/api";
import type {
  EventItem,
  PoolAccount,
  QuotaResponse,
  StatsResponse,
} from "../../types/pool";

export interface AccountsState {
  accounts: PoolAccount[];
  stats: StatsResponse | null;
  events: EventItem[];
  quota: QuotaResponse | null;
  error: string | null;
  quotaError: string | null;
  loading: boolean;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

/**
 * 轮询大盘数据：/api/accounts + /api/stats + /api/events + /api/quota
 * （C1 FR5 + C2 FR7 + C4 事件 + C5 额度）。
 *
 * 设计：链式 setTimeout 避免重叠；后端失败保留上次数据并置 error；cleanup 防竞态。
 * C3：暴露 refresh() 供控制按钮操作后立即拉取（不等下一轮询）。
 * C5：额度走服务端 TTL 缓存（默认 60s），前端常规轮询不会打爆上游；
 * 额度接口失败只影响额度显示，不阻断账号、统计与事件数据；
 * forceRefreshQuota() 供「刷新额度」按钮强制绕过缓存。
 */
export function useAccountPolling(intervalMs = 10_000) {
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [quota, setQuota] = useState<QuotaResponse | null>(null);
  const [quotaBusy, setQuotaBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      fetchAccounts(),
      fetchStats(24),
      fetchEvents(50),
      fetchQuota(), // 非强制：服务端缓存兜底
    ]);
    const coreErrors: string[] = [];
    const [accountsResult, statsResult, eventsResult, quotaResult] = results;

    if (accountsResult.status === "fulfilled") {
      setAccounts(accountsResult.value);
    } else {
      coreErrors.push(errorText(accountsResult.reason));
    }
    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    } else {
      coreErrors.push(errorText(statsResult.reason));
    }
    if (eventsResult.status === "fulfilled") {
      setEvents(eventsResult.value);
    } else {
      coreErrors.push(errorText(eventsResult.reason));
    }
    if (quotaResult.status === "fulfilled") {
      setQuota(quotaResult.value);
      setQuotaError(null);
    } else {
      setQuotaError(errorText(quotaResult.reason));
    }

    setError(coreErrors.length > 0 ? coreErrors.join("；") : null);
    setLoading(false);
  }, []);

  /** C5 FR7：强制刷新额度（?refresh=1），失败保留旧数据并返回错误文案。 */
  const forceRefreshQuota = useCallback(async (): Promise<string | null> => {
    setQuotaBusy(true);
    try {
      const q = await fetchQuota(true);
      setQuota(q);
      setQuotaError(null);
      return null;
    } catch (e) {
      const message = errorText(e);
      setQuotaError(message);
      return message;
    } finally {
      setQuotaBusy(false);
    }
  }, []);

  useEffect(() => {
    let on = true;
    let timer: number | undefined;

    async function tick() {
      if (!on) return;
      await refresh();
      if (on) timer = window.setTimeout(tick, intervalMs);
    }

    void tick();
    return () => {
      on = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [intervalMs, refresh]);

  return {
    accounts,
    stats,
    events,
    quota,
    quotaBusy,
    error,
    quotaError,
    loading,
    refresh,
    forceRefreshQuota,
  };
}
