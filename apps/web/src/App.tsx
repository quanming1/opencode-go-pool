import { Dashboard } from "./features/dashboard/Dashboard";
import "./features/dashboard/dashboard.css";

/**
 * App 单页：页头（项目名 + 版本）+ C1 账号状态大盘。
 */
function App() {
  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">OpenCode Go Pool</h1>
        <span className="page-version">v0.1.0</span>
      </header>
      <main className="page-main">
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
