import { useCallback, useEffect, useState } from "react";
import type { CreatedGatewayKey, GatewayKey } from "../../types/pool";
import { createGatewayKey, fetchGatewayKeys, rememberAdminKey, revokeGatewayKey } from "../../services/api";
import { useI18n } from "../../i18n";

/**
 * Tab2：API Key 管理（C3 FR9；E2 i18n）。
 * - key 列表（label/创建时间/有效|已吊销）
 * - 生成新 key（明文一次性展示 + 复制）
 * - 吊销（二次确认）
 */
export function KeysPanel() {
  const { t } = useI18n();
  const [keys, setKeys] = useState<GatewayKey[]>([]);
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<CreatedGatewayKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);
  // 解锁态：管理请求 401（本浏览器无有效管理凭证）时显示输入框
  const [locked, setLocked] = useState(false);
  const [unlockInput, setUnlockInput] = useState("");

  const reload = useCallback(async () => {
    try {
      setKeys(await fetchGatewayKeys());
      setLocked(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // 401 = 本浏览器没有有效管理凭证（换浏览器/清缓存后的解锁场景）
      if (/401/.test(msg)) {
        setLocked(true);
      } else {
        setError(msg);
      }
    }
  }, []);

  /* eslint-disable react-hooks/set-state-in-effect -- reload 的 setState 均在 await 之后（异步回调），非同步级联渲染 */
  useEffect(() => {
    // 异步加载 key 列表
    void reload();
  }, [reload]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function handleCreate() {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const k = await createGatewayKey(label.trim() || t("keys.unnamed"));
      setCreated(k);
      setLabel("");
      await reload();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/401/.test(msg)) {
        setLocked(true);
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleUnlock() {
    const key = unlockInput.trim();
    if (!key) return;
    rememberAdminKey(key);
    setUnlockInput("");
    await reload();
  }

  async function handleRevoke(id: number) {
    setBusy(true);
    setError(null);
    setConfirmRevoke(null);
    try {
      await revokeGatewayKey(id);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copyKey() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.key);
      setCopied(true);
    } catch {
      setError(t("keys.copyFailed"));
    }
  }

  return (
    <div className="keys-panel" data-testid="keys-panel">
      {locked && (
        <section className="card key-unlock" data-testid="key-unlock">
          <h2 className="card-title">{t("keys.unlockTitle")}</h2>
          <p className="dashboard-empty">{t("keys.unlockTip")}</p>
          <div className="keys-create">
            <input
              type="text"
              className="keys-input"
              placeholder={t("keys.unlockPlaceholder")}
              value={unlockInput}
              onChange={(e) => setUnlockInput(e.target.value)}
              data-testid="unlock-input"
            />
            <button type="button" className="btn btn-primary" onClick={handleUnlock} data-testid="unlock-btn">
              {t("keys.unlock")}
            </button>
          </div>
        </section>
      )}

      <section className="card">
        <h2 className="card-title">{t("keys.createTitle")}</h2>
        <div className="keys-create">
          <input
            type="text"
            className="keys-input"
            placeholder={t("keys.labelPlaceholder")}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            data-testid="key-label-input"
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={handleCreate}
            data-testid="key-create-btn"
          >
            {t("keys.create")}
          </button>
        </div>

        {created && (
          <div className="key-once" data-testid="key-once">
            <p className="key-once__warn">{t("keys.onceWarn")}</p>
            <div className="key-once__row">
              <code className="key-once__code">{created.key}</code>
              <button type="button" className="btn" onClick={copyKey}>
                {copied ? t("keys.copied") : t("keys.copy")}
              </button>
              <button type="button" className="btn" onClick={() => setCreated(null)}>
                {t("keys.saved")}
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">{t("keys.listTitle", { n: keys.length })}</h2>
        {keys.length === 0 ? (
          <p className="dashboard-empty">{t("keys.emptyTip")}</p>
        ) : (
          <div className="keys-table-wrap">
            <table className="keys-table">
              <thead>
                <tr>
                  <th>{t("keys.colLabel")}</th>
                  <th>{t("keys.colCreated")}</th>
                  <th>{t("keys.colStatus")}</th>
                  <th>{t("keys.colAction")}</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id} data-testid={`key-row-${k.id}`}>
                    <td>{k.label}</td>
                    <td>{k.created_at.slice(0, 19).replace("T", " ")}</td>
                    <td>
                      <span className={`badge badge-${k.revoked_at ? "disabled" : "healthy"}`}>
                        {k.revoked_at ? t("keys.revoked") : t("keys.active")}
                      </span>
                    </td>
                    <td>
                      {k.revoked_at ? null : confirmRevoke === k.id ? (
                        <span className="keys-confirm">
                          {t("keys.confirmRevoke")}
                          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => handleRevoke(k.id)}>
                            {t("keys.confirm")}
                          </button>
                          <button type="button" className="btn" onClick={() => setConfirmRevoke(null)}>
                            {t("keys.cancel")}
                          </button>
                        </span>
                      ) : (
                        <button type="button" className="btn" disabled={busy} onClick={() => setConfirmRevoke(k.id)}>
                          {t("keys.revoke")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {error && <p className="dashboard-error" role="alert">{error}</p>}
    </div>
  );
}
