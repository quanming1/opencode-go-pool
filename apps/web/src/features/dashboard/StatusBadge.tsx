import type { AccountStatus } from "../../types/pool";
import { useI18n } from "../../i18n";

/** 状态徽章文案与类名映射（颜色在 CSS 定义：healthy 绿 / cooldown 橙 / disabled 红；E2 i18n）。 */
const STATUS_KEY: Record<AccountStatus, "status.healthy" | "status.cooldown" | "status.disabled"> = {
  healthy: "status.healthy",
  cooldown: "status.cooldown",
  disabled: "status.disabled",
};

export function StatusBadge({ status }: { status: AccountStatus }) {
  const { t } = useI18n();
  const label = t(STATUS_KEY[status] ?? "status.healthy");
  return (
    <span className={`badge badge-${status}`} data-testid="status-badge">
      {label}
    </span>
  );
}
