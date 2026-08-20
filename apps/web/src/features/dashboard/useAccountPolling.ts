import { useEffect, useState } from "react";
import { fetchAccounts } from "../../services/api";
import type { PoolAccount } from "../../types/pool";

export interface AccountsState {
  accounts: PoolAccount[];
  error: string | null;
  loading: boolean;
}

/**
 * 轮询 /api/accounts。
 *
 * 设计（PRD-C1 FR5/AC4）：
 * - 每 intervalMs 拉一次，用链式 setTimeout 避免重叠请求；
 * - 后端失败时保留上次数据并置 error（不清空 UI）；
 * - cleanup 标志 on=false + 清 timer 防竞态/泄漏。
 */
export function useAccountPolling(
  intervalMs = 10_000,
  fetchFn: () => Promise<PoolAccount[]> = fetchAccounts,
): AccountsState {
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    let timer: number | undefined;

    async function tick() {
      try {
        const data = await fetchFn();
        if (!on) return;
        setAccounts(data);
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
  }, [intervalMs, fetchFn]);

  return { accounts, error, loading };
}
