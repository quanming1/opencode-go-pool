import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useI18n, useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";
import { useEChart } from "./useEChart";
import { bucketSuccessRates } from "./chartData";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/**
 * 小时级成功率趋势图（E5 FR3，纯前端）：基于 buckets 逐小时成功率折线。
 * 旧后端（无 success_count）自动回退 request-error 推算；无请求的桶为断点（connectNulls）。
 */
export function SuccessRateTrendChart({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const { theme } = useTheme();

  const ref = useEChart(() => {
    const c = chartColors(theme);
    const data = bucketSuccessRates(stats);
    return {
      tooltip: { trigger: "axis" },
      legend: { data: [t("chart.legend.successRate")], top: 8 },
      grid: { left: 48, right: 32, top: 48, bottom: 36 },
      xAxis: {
        type: "category",
        data: data.map((d) => d.label),
        axisLabel: { interval: 3, color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: {
        type: "value",
        name: "%",
        min: 0,
        max: 100,
        axisLabel: { color: c.label },
      },
      series: [
        {
          name: t("chart.legend.successRate"),
          type: "line",
          connectNulls: true,
          symbolSize: 6,
          data: data.map((d) => d.rate),
          itemStyle: { color: c.ok },
          lineStyle: { width: 2 },
          areaStyle: { color: c.ok, opacity: 0.08 },
        },
      ],
    };
  }, [stats, theme, t]);

  return <div ref={ref} className="chart-box-sm" data-testid="success-rate-trend-chart" />;
}
