/** 颜色 token 唯一 JS 侧来源（E3）：light/dark 两主题 9 色，与 index.css 的 CSS 变量一一对应。
 *
 * 注意：CSS 变量值必须在 index.css（`:root` + `html[data-theme="dark"]`）内联，
 * 浏览器原生主题切换依赖它；ECharts（canvas）无法读 CSS 变量，故本文件提供 JS 侧取值。
 * 两处值的**一致性由 `tokens.test.ts` 硬断言钉死**——任何一边改动若不同步，CI 即红。
 * 新增 JS 侧用色一律从这里取，禁止在组件/图表里裸写 hex。
 */

export type Theme = "light" | "dark";

/** 9 个语义颜色 token（键名与 CSS 变量 `--color-*` 去掉前缀一致）。 */
export interface ColorTokens {
  bg: string;
  "bg-subtle": string;
  text: string;
  "text-secondary": string;
  border: string;
  accent: string;
  ok: string;
  warn: string;
  danger: string;
}

/** 浅色主题 token（必须与 index.css `:root` 块逐条一致）。 */
export const lightTokens: ColorTokens = {
  bg: "#ffffff",
  "bg-subtle": "#f9fafb",
  text: "#1f2937",
  "text-secondary": "#6b7280",
  border: "#e5e7eb",
  accent: "#2563eb",
  ok: "#16a34a",
  warn: "#d97706",
  danger: "#dc2626",
};

/** 深色主题 token（必须与 index.css `html[data-theme="dark"]` 块逐条一致）。 */
export const darkTokens: ColorTokens = {
  bg: "#111827",
  "bg-subtle": "#1f2937",
  text: "#f9fafb",
  "text-secondary": "#9ca3af",
  border: "#374151",
  accent: "#3b82f6",
  ok: "#22c55e",
  warn: "#f59e0b",
  danger: "#ef4444",
};

/** 按主题返回对应 token 集。 */
export function colorTokens(theme: Theme): ColorTokens {
  return theme === "dark" ? darkTokens : lightTokens;
}

/** ECharts 图表派生色板（由 token 派生，不含硬编码）。 */
export interface ChartPalette {
  accent: string;
  ok: string;
  warn: string;
  danger: string;
  border: string;
  label: string;
}

/** 随主题动态取 ECharts 系列色（历史签名：i18n/index.tsx 迁出，语义不变）。 */
export function chartColors(theme: Theme): ChartPalette {
  const c = colorTokens(theme);
  return {
    accent: c.accent,
    ok: c.ok,
    warn: c.warn,
    danger: c.danger,
    border: c.border,
    label: c["text-secondary"],
  };
}
