import * as echarts from "echarts/core";
import { PieChart } from "echarts/charts";
import { LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";
import { useEChart } from "./useEChart";
import { accountTokenShare } from "./chartData";

echarts.use([PieChart, LegendComponent, TooltipComponent, CanvasRenderer]);

/**
 * 账号 Token 占比环图（E5 FR4，纯前端）：per_account 的 token 构成（输入+输出）。
 * 展示各 Key 在总 Token 消耗中的占比与累计请求数。
 */
export function AccountTokenShareChart({ stats }: { stats: StatsResponse }) {
  const { theme } = useTheme();

  const ref = useEChart(() => {
    const c = chartColors(theme);
    const rows = accountTokenShare(stats);
    const palette = [c.accent, c.ok, c.warn, c.danger, c.label, c.border];
    return {
      tooltip: { trigger: "item" },
      legend: { top: 8 },
      series: [
        {
          type: "pie",
          radius: ["42%", "70%"],
          center: ["50%", "60%"],
          label: { color: c.label },
          data: rows.map((r, i) => ({
            name: r.account,
            value: r.tokens,
            itemStyle: { color: palette[i % palette.length] },
          })),
        },
      ],
    };
  }, [stats, theme]);

  return <div ref={ref} className="chart-box-sm" data-testid="account-token-share-chart" />;
}
