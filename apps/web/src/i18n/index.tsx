/* eslint-disable react-refresh/only-export-components -- i18n/theme 为配置型聚合模块（Provider + hooks + 纯函数），非组件快刷场景 */
/** i18n 与主题切换（E2）：I18nProvider / useI18n / useTheme，localStorage 持久化。 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { messages, type Locale, type MessageKey } from "./messages";

export type { Locale, MessageKey } from "./messages";

const LOCALE_KEY = "ocp.locale";
const THEME_KEY = "ocp.theme";
export type Theme = "light" | "dark";

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // localStorage 禁用时降级内存态
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // 忽略：隐私模式/localStorage 禁用
  }
}

function initialLocale(): Locale {
  const stored = safeGet(LOCALE_KEY);
  return stored === "en" ? "en" : "zh";
}

function initialTheme(): Theme {
  const stored = safeGet(THEME_KEY);
  return stored === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export function t(locale: Locale, key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = messages[locale][key] ?? messages.zh[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

export interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    safeSet(LOCALE_KEY, l);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next = prev === "light" ? "dark" : "light";
      safeSet(THEME_KEY, next);
      return next;
    });
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    safeSet(THEME_KEY, next);
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, vars) => t(locale, key, vars),
    }),
    [locale, setLocale],
  );

  const themeValue = useMemo(
    () => ({ theme, toggleTheme, setTheme }),
    [theme, toggleTheme, setTheme],
  );

  return (
    <I18nContext.Provider value={value}>
      <ThemeContext.Provider value={themeValue}>{children}</ThemeContext.Provider>
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

const ThemeContext = createContext<{
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
} | null>(null);

export function useTheme(): {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
} {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within I18nProvider");
  return ctx;
}

/** ECharts 系列色（随主题动态取 CSS 变量）。 */
export function chartColors(theme: Theme): {
  accent: string;
  ok: string;
  danger: string;
  border: string;
  label: string;
} {
  // 直接按主题映射（与 index.css 双主题变量保持一致）
  return {
    accent: theme === "dark" ? "#3b82f6" : "#2563eb",
    ok: theme === "dark" ? "#22c55e" : "#16a34a",
    danger: theme === "dark" ? "#ef4444" : "#dc2626",
    border: theme === "dark" ? "#374151" : "#e5e7eb",
    label: theme === "dark" ? "#9ca3af" : "#6b7280",
  };
}
