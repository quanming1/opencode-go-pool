import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { PieChart } from "echarts/charts";
import { LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { StatsResponse } from "../../types/pool";
import { useTheme } from "../../i18n";
import { chartColors } from "../../theme/tokens";

echarts.use([PieChart, LegendComponent, TooltipComponent, CanvasRenderer]);

/**
 * 协议分布环图（E4 FR7）：近 N 条 request 事件中 responses / chat_completions 占比。
 * 数据来自 stats.summary?.protocol（旧后端缺失时父层显示空态）。
 */
export function ProtocolChart({ stats }: { stats: StatsResponse }) {
  const ref = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const c = chartColors(theme);
    const chart = echarts.init(el);
    const protocol = stats.summary?.protocol ?? [];
    const palette = [c.accent, c.ok, c.danger, c.label, c.border];
    chart.setOption({
      tooltip: { trigger: "item" },
      legend: { top: 8 },
      series: [
        {
          type: "pie",
          radius: ["42%", "70%"],
          center: ["50%", "60%"],
          label: { color: c.label },
          data: protocol.map((p, i) => ({
            name: p.name,
            value: p.count,
            itemStyle: { color: palette[i % palette.length] },
          })),
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [stats, theme]);

  return <div ref={ref} className="chart-box-sm" data-testid="protocol-chart" />;
}
