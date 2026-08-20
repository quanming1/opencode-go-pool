import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { chartColors, useI18n, useTheme } from "../../i18n";

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
    const key = row.model ?? "?";
    byModel.set(key, (byModel.get(key) ?? 0) + row.request_count);
  }
  return [...byModel.entries()]
    .map(([model, count]) => ({ model, count }))
    .sort((a, b) => b.count - a.count);
}

/** 模型请求分布图（D1 FR7；E2 i18n + 主题色）：各模型收到多少次请求。 */
export function ModelUsageChart({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const { theme } = useTheme();
  const data = modelAgg(stats);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors(theme);
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: [t("chart.legend.requestsCount")], top: 8 },
      grid: { left: 56, right: 24, top: 56, bottom: 56 },
      xAxis: {
        type: "category",
        data: data.map((d) => d.model),
        axisLabel: { rotate: 30, interval: 0, color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: { type: "value", name: t("chart.legend.requestsCount"), axisLabel: { color: c.label } },
      series: [
        {
          name: t("chart.legend.requestsCount"),
          type: "bar",
          barMaxWidth: 48,
          data: data.map((d) => d.count),
          itemStyle: { color: c.accent },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="model-usage-chart" />;
}
