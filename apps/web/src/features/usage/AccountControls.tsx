import { useState } from "react";
import type { PoolAccount } from "../../types/pool";
import { clearAccount, disableAccount, enableAccount } from "../../services/api";
import { useI18n } from "../../i18n";

/**
 * 账号控制按钮组（C3 FR8）：
 * 清除冷却（cooldown 时可用）/ 禁用（healthy 时）/ 启用（disabled 时）。
 * 操作成功后回调 onChanged 触发列表刷新。E2 i18n。
 */
export function AccountControls({
  account,
  onChanged,
}: {
  account: PoolAccount;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<{ ok: boolean }>) {
    setBusy(true);
    setError(null);
    try {
      const r = await action();
      if (!r.ok) setError(t("ctrl.failed"));
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const canClear = account.status === "cooldown" && account.enabled;
  const canDisable = account.enabled && account.status !== "disabled";
  const canEnable = !account.enabled || account.status === "disabled";

  return (
    <div className="account-controls">
      {canClear && (
        <button type="button" className="btn" disabled={busy} onClick={() => run(() => clearAccount(account.id))}>
          {t("ctrl.clear")}
        </button>
      )}
      {canDisable && (
        <button type="button" className="btn" disabled={busy} onClick={() => run(() => disableAccount(account.id))}>
          {t("ctrl.disable")}
        </button>
      )}
      {canEnable && (
        <button type="button" className="btn" disabled={busy} onClick={() => run(() => enableAccount(account.id))}>
          {t("ctrl.enable")}
        </button>
      )}
      {error && <span className="account-controls__error">{error}</span>}
    </div>
  );
}

