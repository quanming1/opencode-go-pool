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
import { useI18n, useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";

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
 * 用量趋势图（C2 FR5）：请求量柱状 + 错误柱 + Token 折线，双轴按小时。
 * E2：legend 文案 i18n + 系列色随主题。
 * E4：新增错误系列与成功率 tooltip（chart.tooltip.success）。
 */
export function UsageCharts({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const { theme } = useTheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors(theme);
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const items = (Array.isArray(params) ? params : [params]) as Array<{
            dataIndex?: number;
            marker?: string;
            seriesName?: string;
            value?: number;
          }>;
          const b = stats.buckets[items[0]?.dataIndex ?? 0];
          if (!b) return "";
          const total = (b.error_count ?? 0) + (b.success_count ?? b.request_count);
          const rate =
            total > 0 ? Math.round(((b.success_count ?? (b.request_count - (b.error_count ?? 0))) / total) * 100) : 0;
          const lines = items.map((it) => `${it.marker}${it.seriesName}: ${it.value}`);
          return [
            `<b>${b.ts.slice(11, 16)}</b>`,
            ...lines,
            `${t("chart.legend.successRate")}: ${rate}%`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [
          t("chart.legend.requests"),
          t("chart.legend.token"),
          t("chart.legend.errors"),
        ],
        top: 8,
      },
      grid: { left: 56, right: 56, top: 56, bottom: 32 },
      xAxis: {
        type: "category",
        data: stats.buckets.map((b) => b.ts.slice(11, 16)),
        axisLabel: { color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: [
        { type: "value", name: t("chart.legend.requests"), axisLabel: { color: c.label } },
        { type: "value", name: t("chart.legend.token"), axisLabel: { color: c.label } },
      ],
      series: [
        {
          name: t("chart.legend.requests"),
          type: "bar",
          barMaxWidth: 48,
          data: stats.buckets.map((b) => b.request_count),
          itemStyle: { color: c.accent },
        },
        {
          name: t("chart.legend.errors"),
          type: "bar",
          yAxisIndex: 0,
          barMaxWidth: 24,
          data: stats.buckets.map((b) => b.error_count),
          itemStyle: { color: c.danger, opacity: 0.85 },
        },
        {
          name: t("chart.legend.token"),
          type: "line",
          yAxisIndex: 1,
          data: stats.buckets.map((b) => b.prompt_tokens + b.completion_tokens),
          itemStyle: { color: c.ok },
          lineStyle: { width: 2 },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [stats, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="usage-chart" />;
}
