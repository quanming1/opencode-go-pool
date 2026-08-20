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

function modelAgg(stats: StatsResponse): Array<{ model: string; count: number }> {
  const byModel = new Map<string, number>();
  for (const row of stats.per_account_models) {
    const key = row.model ?? "未知模型";
    byModel.set(key, (byModel.get(key) ?? 0) + row.request_count);
  }
  return [...byModel.entries()]
    .map(([model, count]) => ({ model, count }))
    .sort((a, b) => b.count - a.count);
}

/** 模型请求分布图（D1 FR7）：各模型收到多少次请求。 */
export function ModelUsageChart({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);
  const data = modelAgg(stats);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["请求数"], top: 8 },
      grid: { left: 56, right: 24, top: 56, bottom: 56 },
      xAxis: {
        type: "category",
        data: data.map((d) => d.model),
        axisLabel: { rotate: 30, interval: 0 },
      },
      yAxis: { type: "value", name: "请求数" },
      series: [
        {
          name: "请求数",
          type: "bar",
          barMaxWidth: 48,
          data: data.map((d) => d.count),
          itemStyle: { color: "#2563eb" },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  return <div ref={ref} className="chart-box" data-testid="model-usage-chart" />;
}
