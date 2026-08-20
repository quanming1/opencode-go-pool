import type { AccountStatus } from "../../types/pool";

/** 状态徽章文案与类名映射（颜色在 CSS 定义：healthy 绿 / cooldown 橙 / disabled 红）。 */
const STATUS_META: Record<AccountStatus, { label: string }> = {
  healthy: { label: "健康" },
  cooldown: { label: "冷却中" },
  disabled: { label: "已禁用" },
};

export function StatusBadge({ status }: { status: AccountStatus }) {
  const meta = STATUS_META[status] ?? { label: status };
  return (
    <span className={`badge badge-${status}`} data-testid="status-badge">
      {meta.label}
    </span>
  );
}
