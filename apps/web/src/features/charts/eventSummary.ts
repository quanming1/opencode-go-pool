/** 统一事件摘要（C4；E2 i18n）：类型标签映射 + 按 data 渲染摘要文本。

 * buildSummary / labelOf 接收翻译函数 t（由调用方从 useI18n() 传入），
 * 保持纯函数可测：测试传返回中文的 stub t 即可。
 */
import type { MessageKey } from "../../i18n";

export type TranslateFn = (
  key: MessageKey,
  vars?: Record<string, string | number>,
) => string;

/** 事件类型 → 翻译键。 */
const EVENT_LABEL_KEYS: Record<string, MessageKey> = {
  request: "event.label.request",
  key_cooldown_started: "event.label.key_cooldown_started",
  key_cooldown_completed: "event.label.key_cooldown_completed",
  key_switch: "event.label.key_switch",
  all_keys_invalid: "event.label.all_keys_invalid",
  all_keys_unavailable: "event.label.all_keys_unavailable",
  key_disabled: "event.label.key_disabled",
  key_enabled: "event.label.key_enabled",
  key_cooldown_cleared: "event.label.key_cooldown_cleared",
  gateway_key_created: "event.label.gateway_key_created",
  gateway_key_revoked: "event.label.gateway_key_revoked",
};

export function labelOf(type: string, t: TranslateFn): string {
  const key = EVENT_LABEL_KEYS[type];
  return key ? t(key) : type;
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

/** 按事件类型渲染摘要文本（data 业务内容）；正文段由 t 本地化。 */
export function buildSummary(
  type: string,
  data: Record<string, unknown>,
  t: TranslateFn,
): string {
  switch (type) {
    case "request": {
      const success = data["success"] === true;
      const tag = success ? t("event.success") : t("event.failed");
      const model = str(data, "model", "-");
      const protocol = str(data, "protocol", "-");
      const status = str(data, "status_code", "-");
      const dur = `${str(data, "duration_ms", "0")}ms`;
      const attempts = t("event.attempts", { n: str(data, "attempt_count", "0") });
      const token = (data["token"] as { prompt?: number; completion?: number }) ?? {};
      const tok = `tok ${Number(token.prompt ?? 0)}/${Number(token.completion ?? 0)}`;
      return `${tag} ${protocol} ${model} HTTP ${status} ${dur} ${attempts} ${tok}`;
    }
    case "key_switch": {
      const errorType = str(data, "error_type");
      const reason = str(data, "reason");
      const err = errorType ? t("event.autoJoin", { x: errorType }) : "";
      const r = reason ? t("event.reasonJoin", { r: reason }) : "";
      return `${str(data, "from_account_id", "-")} → ${str(data, "to_account_id", "-")}${err}${r}`;
    }
    case "key_cooldown_started": {
      const errorType = str(data, "error_type");
      const reason = str(data, "reason");
      const err = errorType ? t("event.autoJoin", { x: errorType }) : "";
      const r = reason ? t("event.reasonJoin", { r: reason }) : "";
      return `${str(data, "account_id", "-")}${err}${r}`;
    }
    case "key_cooldown_completed": {
      const st = str(data, "previous_status");
      const reason = str(data, "reason");
      return `${str(data, "account_id", "-")}${st ? t("event.originalJoin", { st }) : ""}${reason ? t("event.reasonJoin", { r: reason }) : t("event.recovered")}`;
    }
    case "all_keys_invalid":
      return `${accountList(data)}${t("event.reasonJoin", { r: t("event.errorTypes", { t: (data["error_types"] as string[] ?? []).join("/") || "-" }) })}${t("event.reasonJoin", { r: t("event.attempts", { n: str(data, "attempt_count", "0") }) })}`;
    case "all_keys_unavailable":
      return `${accountList(data) || t("event.noHealthy")}${(data["error_types"] as string[] ?? []).length ? t("event.reasonJoin", { r: t("event.errorTypes", { t: (data["error_types"] as string[] ?? []).join("/") }) }) : ""}`;
    case "key_disabled":
      return `${str(data, "account_id", "-")}${data["automatic"] === true ? t("event.autoJoin", { x: t("event.automatic") }) : t("event.autoJoin", { x: t("event.manual") })}${str(data, "reason") ? t("event.reasonJoin", { r: str(data, "reason") }) : ""}`;
    case "key_enabled":
      return `${str(data, "account_id", "-")}${str(data, "reason") ? t("event.reasonJoin", { r: str(data, "reason") }) : ""}`;
    case "key_cooldown_cleared":
      return `${str(data, "account_id", "-")}${str(data, "previous_status") ? t("event.originalJoin", { st: str(data, "previous_status") }) : ""}${str(data, "reason") ? t("event.reasonJoin", { r: str(data, "reason") }) : t("event.clearCooldown")}`;
    case "gateway_key_created":
      return `#${str(data, "key_id", "-")}（${str(data, "label", "-")}）`;
    case "gateway_key_revoked":
      return `#${str(data, "key_id", "-")}（${str(data, "label", "-")}）`;
    default:
      return JSON.stringify(data);
  }
}
