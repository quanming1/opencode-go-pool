/** 额度展示格式化（C5 FR4）：倒计时文案与进度条色阶。 */

/**
 * 重置倒计时文案（对齐用户控制台原话格式）：
 * - < 1 小时：`X 分钟`（0 → 即将重置）
 * - < 1 天：`X 小时 Y 分钟`
 * - >= 1 天：`X 天 Y 小时`
 */
export function resetsInText(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds <= 0) return "即将重置";
  const totalMin = Math.floor(seconds / 60);
  if (totalMin < 1) return "即将重置";
  if (totalMin < 60) return `${totalMin} 分钟`;
  const hours = Math.floor(totalMin / 60);
  const minutes = totalMin % 60;
  if (hours < 24) return `${hours} 小时 ${minutes} 分钟`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return `${days} 天 ${remHours} 小时`;
}

/** 进度条色阶：限额/满额红色，>= 80 橙色，其余绿色。 */
export function quotaTone(percent: number, status: string): "ok" | "warn" | "danger" {
  if (status === "rate-limited" || percent >= 100) return "danger";
  if (percent >= 80) return "warn";
  return "ok";
}
