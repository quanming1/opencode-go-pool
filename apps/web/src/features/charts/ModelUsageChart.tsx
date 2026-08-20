import { useMemo } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useI18n, useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";
import { useEChart } from "./useEChart";

echarts.use([
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

function modelAgg(stats: StatsResponse): Array<{
  model: string;
  count: number;
  success: number;
  error: number;
  tokens: number;
  rate: number;
}> {
  const byModel = new Map<
    string,
    { count: number; success: number; error: number; tokens: number }
  >();
  for (const row of stats.per_account_models) {
    const key = row.model ?? "?";
    const cur = byModel.get(key) ?? { count: 0, success: 0, error: 0, tokens: 0 };
    cur.count += row.request_count;
    cur.success += row.success_count ?? 0;
    cur.error += row.error_count;
    cur.tokens += row.prompt_tokens + row.completion_tokens;
    byModel.set(key, cur);
  }
  return [...byModel.entries()]
    .map(([model, v]) => ({
      model,
      count: v.count,
      success: v.success,
      error: v.error,
      tokens: v.tokens,
      rate: v.count > 0 ? Math.round((v.success / v.count) * 100) : 0,
    }))
    .sort((a, b) => b.count - a.count);
}

/**
 * 模型请求分布图（D1 FR7；E2 i18n/主题；E4 加错误系列与 token/成功率 tooltip）：
 * 各模型收到多少次请求、多少次错误，以及累计 token 与成功率。
 */
export function ModelUsageChart({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const { theme } = useTheme();
  // useMemo：stats 不变时不重建数据，避免每 render 重绘图表
  const data = useMemo(() => modelAgg(stats), [stats]);

  const ref = useEChart(() => {
    const c = chartColors(theme);
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
          const d = data[items[0]?.dataIndex ?? 0];
          if (!d) return "";
          const lines = items.map((it) => `${it.marker}${it.seriesName}: ${it.value}`);
          return [
            `<b>${d.model}</b>`,
            ...lines,
            `${t("chart.legend.token")}: ${d.tokens}`,
            `${t("chart.legend.successRate")}: ${d.rate}%`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [t("chart.legend.requestsCount"), t("chart.legend.errors")],
        top: 8,
      },
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
          barMaxWidth: 40,
          data: data.map((d) => d.count),
          itemStyle: { color: c.accent },
        },
        {
          name: t("chart.legend.errors"),
          type: "bar",
          barMaxWidth: 20,
          data: data.map((d) => d.error),
          itemStyle: { color: c.danger, opacity: 0.85 },
        },
      ],
    };
  }, [data, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="model-usage-chart" />;
}
