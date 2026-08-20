import { useState } from "react";
import { Sidebar, type TabId } from "./components/Sidebar";
import { UsagePanel } from "./features/usage/UsagePanel";
import { KeysPanel } from "./features/keys/KeysPanel";
import { useI18n, useTheme, type Locale, type Theme } from "./i18n";
import "./features/dashboard/dashboard.css";
import "./layout.css";

/**
 * App：左右分栏布局（C3 FR7）——左侧 tab 导航，右侧内容区。
 * Tab1 用量信息（UsagePanel）；Tab2 API Key 管理（KeysPanel）。
 * E2：header 右侧语言与主题切换控件。
 */
function App() {
  const [tab, setTab] = useState<TabId>("usage");
  const { locale, setLocale, t } = useI18n();
  const { theme, setTheme } = useTheme();

  const switchLocale = (l: Locale): void => setLocale(l);
  const switchTheme = (x: Theme): void => setTheme(x);

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">OpenCode Go Pool</h1>
        <span className="page-version">v0.3.0</span>
        <div className="page-switch" data-testid="locale-switch">
          <button
            type="button"
            className={`btn${locale === "zh" ? " btn-primary" : ""}`}
            onClick={() => switchLocale("zh")}
            data-testid="locale-zh"
          >
            中文
          </button>
          <button
            type="button"
            className={`btn${locale === "en" ? " btn-primary" : ""}`}
            onClick={() => switchLocale("en")}
            data-testid="locale-en"
          >
            EN
          </button>
        </div>
        <div className="page-switch" data-testid="theme-switch">
          <button
            type="button"
            className={`btn${theme === "light" ? " btn-primary" : ""}`}
            onClick={() => switchTheme("light")}
            data-testid="theme-light"
          >
            {t("app.light")}
          </button>
          <button
            type="button"
            className={`btn${theme === "dark" ? " btn-primary" : ""}`}
            onClick={() => switchTheme("dark")}
            data-testid="theme-dark"
          >
            {t("app.dark")}
          </button>
        </div>
      </header>
      <div className="page-body">
        <Sidebar active={tab} onChange={setTab} />
        <main className="page-main">
          {tab === "usage" ? <UsagePanel /> : <KeysPanel />}
        </main>
      </div>
    </div>
  );
}

export default App;
