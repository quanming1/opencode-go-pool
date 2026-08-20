import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { I18nProvider } from "./i18n";
import "./index.css";

// E2：渲染前应用持久化主题，避免首帧闪烁（localStorage 无值时默认浅色）
{
  try {
    const theme = localStorage.getItem("ocp.theme");
    document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
  } catch {
    document.documentElement.dataset.theme = "light";
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>,
);

