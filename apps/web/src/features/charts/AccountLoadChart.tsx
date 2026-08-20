import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";

echarts.use([
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

/** 账号负载图（D1 FR7）：各 Key 收到多少请求、多少错误。 */
export function AccountLoadChart({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    const accounts = stats.per_account;
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["请求数", "错误数"], top: 8 },
      grid: { left: 56, right: 24, top: 56, bottom: 56 },
      xAxis: {
        type: "category",
        data: accounts.map((a) => a.account_id),
        axisLabel: { rotate: 30, interval: 0 },
      },
      yAxis: { type: "value", name: "次数" },
      series: [
        {
          name: "请求数",
          type: "bar",
          barMaxWidth: 32,
          data: accounts.map((a) => a.request_count),
          itemStyle: { color: "#2563eb" },
        },
        {
          name: "错误数",
          type: "bar",
          barMaxWidth: 32,
          data: accounts.map((a) => a.error_count),
          itemStyle: { color: "#dc2626" },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [stats.per_account]);

  return <div ref={ref} className="chart-box" data-testid="account-load-chart" />;
}
