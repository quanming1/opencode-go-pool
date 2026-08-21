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
import { useEChart } from "./useEChart";

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
 * 用量趋势图（C2 FR5）：请求量柱 + 错误柱 + Token（输入/输出）堆叠柱，双轴按小时。
 * E2：legend i18n + 系列色随主题；E4：错误系列与成功率 tooltip。
 * E5：Token 拆 prompt/completion 堆叠（输入绿/输出橙）；X 轴标签随周期自适应
 *（≤48h 显示 HH:MM，>48h 显示 MM-DD HH:MM）。
 */
export function UsageCharts({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const { theme } = useTheme();

  const ref = useEChart(() => {
    const c = chartColors(theme);
    const longWindow = stats.hours > 48;
    const fmt = (ts: string): string => (longWindow ? ts.slice(5, 16) : ts.slice(11, 16));
    return {
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
          const total = (b.error_count ?? 0) + (b.success_count ?? (b.request_count - (b.error_count ?? 0)));
          const rate =
            total > 0 ? Math.round(((b.success_count ?? (b.request_count - (b.error_count ?? 0))) / total) * 100) : 0;
          const lines = items.map((it) => `${it.marker}${it.seriesName}: ${it.value}`);
          return [
            `<b>${fmt(b.ts)}</b>`,
            ...lines,
            `${t("chart.legend.successRate")}: ${rate}%`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [
          t("chart.legend.requests"),
          t("chart.legend.errors"),
          t("chart.legend.prompt"),
          t("chart.legend.completion"),
        ],
        top: 8,
      },
      grid: { left: 56, right: 56, top: 56, bottom: 32 },
      xAxis: {
        type: "category",
        data: stats.buckets.map((b) => fmt(b.ts)),
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
          name: t("chart.legend.prompt"),
          type: "bar",
          stack: "token",
          yAxisIndex: 1,
          data: stats.buckets.map((b) => b.prompt_tokens),
          itemStyle: { color: c.ok },
        },
        {
          name: t("chart.legend.completion"),
          type: "bar",
          stack: "token",
          yAxisIndex: 1,
          data: stats.buckets.map((b) => b.completion_tokens),
          itemStyle: { color: c.warn },
        },
      ],
    };
  }, [stats, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="usage-chart" />;
}
