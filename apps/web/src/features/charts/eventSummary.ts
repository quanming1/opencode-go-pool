/** 统一事件摘要（C4）：类型标签映射 + 按 data 渲染摘要文本。 */

/** 事件类型 → 中文标签。 */
export const EVENT_LABELS: Record<string, string> = {
  request: "请求",
  key_cooldown_started: "进入冷却",
  key_cooldown_completed: "冷却完成",
  key_switch: "切换",
  all_keys_invalid: "全部额度/鉴权失效",
  all_keys_unavailable: "全部不可用",
  key_disabled: "禁用",
  key_enabled: "启用",
  key_cooldown_cleared: "清除冷却",
  gateway_key_created: "网关Key创建",
  gateway_key_revoked: "网关Key吊销",
};

export function labelOf(type: string): string {
  return EVENT_LABELS[type] ?? type;
}

function str(data: Record<string, unknown>, key: string, fallback = ""): string {
  const v = data[key];
  return v === undefined || v === null ? fallback : String(v);
}

function accountList(data: Record<string, unknown>): string {
  const ids = data["attempted_account_ids"];
  if (Array.isArray(ids) && ids.length > 0) return ids.join(", ");
  const single = str(data, "account_id");
  return single || "-";
}

/** 按事件类型渲染摘要文本（data 业务内容）。 */
export function buildSummary(type: string, data: Record<string, unknown>): string {
  switch (type) {
    case "request": {
      const success = data["success"] === true;
      const tag = success ? "成功" : "失败";
      const model = str(data, "model", "-");
      const protocol = str(data, "protocol", "-");
      const status = str(data, "status_code", "-");
      const dur = `${str(data, "duration_ms", "0")}ms`;
      const attempts = `尝试 ${str(data, "attempt_count", "0")} 次`;
      const token = (data["token"] as { prompt?: number; completion?: number }) ?? {};
      const tok = `tok ${Number(token.prompt ?? 0)}/${Number(token.completion ?? 0)}`;
      return `${tag} ${protocol} ${model} HTTP ${status} ${dur} ${attempts} ${tok}`;
    }
    case "key_switch": {
      const errorType = str(data, "error_type");
      const reason = str(data, "reason");
      return `${str(data, "from_account_id", "-")} → ${str(data, "to_account_id", "-")}${errorType ? `（${errorType}）` : ""}${reason ? `：${reason}` : ""}`;
    }
    case "key_cooldown_started": {
      const errorType = str(data, "error_type");
      const reason = str(data, "reason");
      return `${str(data, "account_id", "-")}${errorType ? `（${errorType}）` : ""}${reason ? `：${reason}` : ""}`;
    }
    case "key_cooldown_completed":
      return `${str(data, "account_id", "-")}${str(data, "previous_status") ? `（原 ${str(data, "previous_status")}）` : ""}：${str(data, "reason", "已恢复")}`;
    case "all_keys_invalid":
      return `${accountList(data)}，错误类型 ${(data["error_types"] as string[] ?? []).join("/") || "-"}，尝试 ${str(data, "attempt_count", "0")} 次`;
    case "all_keys_unavailable":
      return `${accountList(data) || "无健康账号"}，错误类型 ${(data["error_types"] as string[] ?? []).join("/") || "无"}`;
    case "key_disabled":
      return `${str(data, "account_id", "-")}${data["automatic"] === true ? "（自动）" : "（手动）"}${str(data, "reason") ? `：${str(data, "reason")}` : ""}`;
    case "key_enabled":
      return `${str(data, "account_id", "-")}${str(data, "reason") ? `：${str(data, "reason")}` : ""}`;
    case "key_cooldown_cleared":
      return `${str(data, "account_id", "-")}${str(data, "previous_status") ? `（原 ${str(data, "previous_status")}）` : ""}：${str(data, "reason", "清除冷却")}`;
    case "gateway_key_created":
      return `#${str(data, "key_id", "-")}（${str(data, "label", "-")}）`;
    case "gateway_key_revoked":
      return `#${str(data, "key_id", "-")}（${str(data, "label", "-")}）`;
    default:
      return JSON.stringify(data);
  }
}