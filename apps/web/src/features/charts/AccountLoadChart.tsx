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

/** 账号负载图（D1 FR7；E2 i18n + 主题色）：各 Key 收到多少请求、多少错误。 */
export function AccountLoadChart({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const { theme } = useTheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors(theme);
    const chart = echarts.init(el);
    const accounts = stats.per_account;
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: {
        data: [t("chart.legend.requestsCount"), t("chart.legend.errors")],
        top: 8,
      },
      grid: { left: 56, right: 24, top: 56, bottom: 56 },
      xAxis: {
        type: "category",
        data: accounts.map((a) => a.account_id),
        axisLabel: { rotate: 30, interval: 0, color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: { type: "value", name: t("chart.legend.requestsCount"), axisLabel: { color: c.label } },
      series: [
        {
          name: t("chart.legend.requestsCount"),
          type: "bar",
          barMaxWidth: 32,
          data: accounts.map((a) => a.request_count),
          itemStyle: { color: c.accent },
        },
        {
          name: t("chart.legend.errors"),
          type: "bar",
          barMaxWidth: 32,
          data: accounts.map((a) => a.error_count),
          itemStyle: { color: c.danger },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [stats.per_account, theme, t]);

  return <div ref={ref} className="chart-box" data-testid="account-load-chart" />;
}
