import { useCallback, useEffect, useState } from "react";
import type { CreatedGatewayKey, GatewayKey } from "../../types/pool";
import { createGatewayKey, fetchGatewayKeys, revokeGatewayKey } from "../../services/api";

/**
 * Tab2：API Key 管理（C3 FR9）。
 * - key 列表（label/创建时间/有效|已吊销）
 * - 生成新 key（明文一次性展示 + 复制）
 * - 吊销（二次确认）
 */
export function KeysPanel() {
  const [keys, setKeys] = useState<GatewayKey[]>([]);
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<CreatedGatewayKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);

  const reload = useCallback(async () => {
    try {
      setKeys(await fetchGatewayKeys());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
      const k = await createGatewayKey(label.trim() || "unnamed");
      setCreated(k);
      setLabel("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
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
      setError("复制失败，请手动复制");
    }
  }

  return (
    <div className="keys-panel" data-testid="keys-panel">
      <section className="card">
        <h2 className="card-title">生成新 Key</h2>
        <div className="keys-create">
          <input
            type="text"
            className="keys-input"
            placeholder="标签（如 ftre）"
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
            生成
          </button>
        </div>

        {created && (
          <div className="key-once" data-testid="key-once">
            <p className="key-once__warn">
              明文 key 仅显示这一次，请立即复制保存（用于客户端 Authorization: Bearer 头）：
            </p>
            <div className="key-once__row">
              <code className="key-once__code">{created.key}</code>
              <button type="button" className="btn" onClick={copyKey}>
                {copied ? "已复制" : "复制"}
              </button>
              <button type="button" className="btn" onClick={() => setCreated(null)}>
                我已保存
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">已有 Key（{keys.length}）</h2>
        {keys.length === 0 ? (
          <p className="dashboard-empty">暂无 key。生成后转发端点将启用 Bearer 鉴权。</p>
        ) : (
          <table className="keys-table">
            <thead>
              <tr>
                <th>标签</th>
                <th>创建时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} data-testid={`key-row-${k.id}`}>
                  <td>{k.label}</td>
                  <td>{k.created_at.slice(0, 19).replace("T", " ")}</td>
                  <td>
                    <span className={`badge badge-${k.revoked_at ? "disabled" : "healthy"}`}>
                      {k.revoked_at ? "已吊销" : "有效"}
                    </span>
                  </td>
                  <td>
                    {k.revoked_at ? null : confirmRevoke === k.id ? (
                      <span className="keys-confirm">
                        确认吊销？
                        <button type="button" className="btn btn-danger" disabled={busy} onClick={() => handleRevoke(k.id)}>
                          确认
                        </button>
                        <button type="button" className="btn" onClick={() => setConfirmRevoke(null)}>
                          取消
                        </button>
                      </span>
                    ) : (
                      <button type="button" className="btn" disabled={busy} onClick={() => setConfirmRevoke(k.id)}>
                        吊销
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && <p className="dashboard-error" role="alert">{error}</p>}
    </div>
  );
}
