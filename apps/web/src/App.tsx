import { useState } from "react";
import { Sidebar, type TabId } from "./components/Sidebar";
import { UsagePanel } from "./features/usage/UsagePanel";
import { KeysPanel } from "./features/keys/KeysPanel";
import "./features/dashboard/dashboard.css";
import "./layout.css";

/**
 * App：左右分栏布局（C3 FR7）——左侧 tab 导航，右侧内容区。
 * Tab1 用量信息（UsagePanel）；Tab2 API Key 管理（KeysPanel）。
 */
function App() {
  const [tab, setTab] = useState<TabId>("usage");

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">OpenCode Go Pool</h1>
        <span className="page-version">v0.1.0</span>
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
