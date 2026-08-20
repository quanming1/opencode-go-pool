import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useI18n, useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";
import { useEChart } from "./useEChart";

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/** 账号负载图（D1 FR7；E2 i18n/主题；E4 加成功率折线与 token tooltip）：
 * 各 Key 收到多少次请求、多少次错误，以及成功率（右轴 %）。 */
export function AccountLoadChart({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const { theme } = useTheme();

  const ref = useEChart(() => {
    const c = chartColors(theme);
    const accounts = stats.per_account;
    const rateOf = (a: { request_count: number; error_count: number; success_count?: number }): number => {
      const err = a.error_count;
      const ok = a.success_count ?? (a.request_count - err);
      const total = ok + err;
      return total > 0 ? Math.round((ok / total) * 100) : 0;
    };
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
          const a = accounts[items[0]?.dataIndex ?? 0];
          if (!a) return "";
          const lines = items.map((it) => `${it.marker}${it.seriesName}: ${it.value}`);
          return [
            `<b>${a.account_id}</b>`,
            ...lines,
            `${t("chart.legend.token")}: ${a.prompt_tokens + a.completion_tokens}`,
          ].join("<br/>");
        },
      },
      legend: {
        data: [
          t("chart.legend.requestsCount"),
          t("chart.legend.errors"),
          t("chart.legend.successRate"),
        ],
        top: 8,
      },
      grid: { left: 56, right: 56, top: 56, bottom: 56 },
      xAxis: {
        type: "category",
        data: accounts.map((a) => a.account_id),
        axisLabel: { rotate: 30, interval: 0, color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: [
        { type: "value", name: t("chart.legend.requestsCount"), axisLabel: { color: c.label } },
        {
          type: "value",
          name: t("chart.legend.successRate"),
          min: 0,
          max: 100,
          axisLabel: { color: c.label },
        },
      ],
      series: [
        {
          name: t("chart.legend.requestsCount"),
          type: "bar",
          barMaxWidth: 24,
          data: accounts.map((a) => a.request_count),
          itemStyle: { color: c.accent },
        },
        {
          name: t("chart.legend.errors"),
          type: "bar",
          barMaxWidth: 18,
          data: accounts.map((a) => a.error_count),
          itemStyle: { color: c.danger, opacity: 0.85 },
        },
        {
          name: t("chart.legend.successRate"),
          type: "line",
          yAxisIndex: 1,
          data: accounts.map(rateOf),
          itemStyle: { color: c.ok },
          lineStyle: { width: 2 },
        },
      ],
    };
  }, [stats.per_account, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="account-load-chart" />;
}
