import { useCallback, useEffect, useState } from "react";
import {
  fetchAccounts,
  fetchEvents,
  fetchStats,
} from "../../services/api";
import type { EventItem, PoolAccount, StatsResponse } from "../../types/pool";

export interface AccountsState {
  accounts: PoolAccount[];
  stats: StatsResponse | null;
  events: EventItem[];
  error: string | null;
  loading: boolean;
}

/**
 * 轮询大盘数据：/api/accounts + /api/stats + /api/events（C1 FR5 + C2 FR7 + C4 FR）。
 *
 * 设计：链式 setTimeout 避免重叠；后端失败保留上次数据并置 error；cleanup 防竞态。
 * C3：暴露 refresh() 供控制按钮操作后立即拉取（不等下一轮询）。
 * C4：时间线统一消费 /api/events（type/data/meta/time）。
 */
export function useAccountPolling(intervalMs = 10_000) {
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [accs, s, ev] = await Promise.all([
        fetchAccounts(),
        fetchStats(24),
        fetchEvents(50),
      ]);
      setAccounts(accs);
      setStats(s);
      setEvents(ev);
      setError(null);
      setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
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

  return { accounts, stats, events, error, loading, refresh };
}