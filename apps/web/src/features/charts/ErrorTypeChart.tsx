import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useI18n, useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";
import { useEChart } from "./useEChart";

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/**
 * 错误类型分布图（E4 FR7）：近端错误按 error_type 分组计数（quota/server/auth/...）。
 * 数据来自 stats.error_types（旧后端缺失时父层显示空态）。
 */
export function ErrorTypeChart({ stats }: { stats: StatsResponse }) {
  const { t } = useI18n();
  const { theme } = useTheme();

  const ref = useEChart(() => {
    const c = chartColors(theme);
    const types = stats.error_types ?? [];
    return {
      tooltip: { trigger: "axis" },
      legend: { data: [t("chart.legend.errors")], top: 8 },
      grid: { left: 72, right: 24, top: 48, bottom: 36 },
      xAxis: {
        type: "category",
        data: types.map((e) => e.type),
        axisLabel: { rotate: 20, interval: 0, color: c.label },
        axisLine: { lineStyle: { color: c.border } },
      },
      yAxis: { type: "value", name: t("chart.legend.errors"), axisLabel: { color: c.label } },
      series: [
        {
          name: t("chart.legend.errors"),
          type: "bar",
          barMaxWidth: 40,
          data: types.map((e) => e.count),
          itemStyle: { color: c.danger },
        },
      ],
    };
  }, [stats, theme, t]);

  return <div ref={ref} className="chart-box-sm" data-testid="error-type-chart" />;
}
