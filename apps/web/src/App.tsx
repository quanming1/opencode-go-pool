import { DemoChart } from "./features/demo/DemoChart";

/**
 * App 单页（骨架阶段）：
 * 页头（项目名 + 版本）+ 主区（欢迎占位卡片 + ECharts 示例图）。
 * C 阶段替换为账号状态大盘与用量趋势。
 */
function App() {
  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">OpenCode Go Pool</h1>
        <span className="page-version">v0.1.0</span>
      </header>
      <main className="page-main">
        <section className="card">
          <h2 className="card-title">欢迎</h2>
          <p className="card-text">
            多个 OpenCode Go 订阅账号合并为一个逻辑上游的代理服务。监控台建设中。
          </p>
        </section>
        <section className="card">
          <h2 className="card-title">用量趋势（示例）</h2>
          <DemoChart />
        </section>
      </main>
    </div>
  );
}

export default App;
