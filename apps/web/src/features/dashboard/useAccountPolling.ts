import { useEffect, useState } from "react";
import {
  fetchAccounts,
  fetchStats,
  fetchSwitchHistory,
} from "../../services/api";
import type { PoolAccount, StatsResponse, SwitchEvent } from "../../types/pool";

export interface AccountsState {
  accounts: PoolAccount[];
  stats: StatsResponse | null;
  switchEvents: SwitchEvent[];
  error: string | null;
  loading: boolean;
}

/**
 * 轮询大盘数据：/api/accounts + /api/stats + /api/switch-history（C1 FR5 + C2 FR7）。
 *
 * 设计：链式 setTimeout 避免重叠；后端失败保留上次数据并置 error；cleanup 防竞态。
 */
export function useAccountPolling(intervalMs = 10_000) {
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [switchEvents, setSwitchEvents] = useState<SwitchEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    let timer: number | undefined;

    async function tick() {
      try {
        const [accs, s, ev] = await Promise.all([
          fetchAccounts(),
          fetchStats(24),
          fetchSwitchHistory(50),
        ]);
        if (!on) return;
        setAccounts(accs);
        setStats(s);
        setSwitchEvents(ev);
        setError(null);
        setLoading(false);
      } catch (e) {
        if (!on) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      } finally {
        if (on) timer = window.setTimeout(tick, intervalMs);
      }
    }

    void tick();
    return () => {
      on = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [intervalMs]);

  return { accounts, stats, switchEvents, error, loading };
}
