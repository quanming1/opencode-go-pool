import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";

// 按需注册（A3 DemoChart 同模式）
echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

/**
 * 用量趋势图（C2 FR5）：请求量柱状 + Token 用量折线，双轴按小时。
 * 渲染逻辑依赖 canvas，jsdom 无法执行 → 组件测试只 mock 掉本组件。
 */
export function UsageCharts({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["请求量", "Token"] },
      grid: { left: 56, right: 56, top: 32, bottom: 32 },
      xAxis: {
        type: "category",
        data: stats.buckets.map((b) => b.ts.slice(11, 16)),
      },
      yAxis: [
        { type: "value", name: "请求量" },
        { type: "value", name: "Token" },
      ],
      series: [
        {
          name: "请求量",
          type: "bar",
          data: stats.buckets.map((b) => b.request_count),
          itemStyle: { color: "#2563eb" },
        },
        {
          name: "Token",
          type: "line",
          yAxisIndex: 1,
          data: stats.buckets.map((b) => b.prompt_tokens + b.completion_tokens),
          itemStyle: { color: "#16a34a" },
          lineStyle: { width: 2 },
        },
      ],
    });
    return () => chart.dispose();
  }, [stats]);

  return <div ref={ref} className="chart-box" data-testid="usage-chart" />;
}
