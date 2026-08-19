import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

// 按需注册（控制产物体积，见 PRD-A3 §3）
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

/** ECharts 示例折线图（骨架阶段：静态数据，C 阶段替换为真实用量）。 */
export function DemoChart() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 48, right: 24, top: 24, bottom: 32 },
      xAxis: {
        type: "category",
        data: ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00"],
      },
      yAxis: { type: "value" },
      series: [
        {
          name: "请求数",
          type: "line",
          data: [120, 200, 150, 80, 170, 190],
          itemStyle: { color: "#2563eb" },
          lineStyle: { width: 2 },
        },
      ],
    });
    return () => chart.dispose();
  }, []);

  return <div ref={ref} className="chart-box" data-testid="demo-chart" />;
}
