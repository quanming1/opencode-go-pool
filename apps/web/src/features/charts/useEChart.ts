import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import * as echarts from "echarts/core";
import type { ECharts, EChartsCoreOption } from "echarts/core";

/**
 * ECharts 实例生命周期 hook（G5 FR1）。
 *
 * 背景：E3-E5 演进出 7 个图表组件，各自内联「init + setOption + resize 监听 + dispose」
 * 的生命周期样板（约 14 行 × 7）。此 hook 把这套样板收敛为单一实现：
 * - 首挂载对 ref 元素 init（用 getInstanceByDom 复用已有实例，避免 StrictMode 双挂载重复 init）；
 * - 之后 deps 变化仅 setOption 更新、不复建实例——大盘轮询每 10s 更新 stats 时
 *   不再反复销毁重建 canvas（性能）；notMerge 保证全量替换旧 option；
 * - 统一 window resize 监听；真卸载时用 chartRef dispose（不依赖重新查询 DOM 绑定）。
 */
export function useEChart<T extends object>(
  makeOption: () => T,
  deps: readonly unknown[],
): RefObject<HTMLDivElement | null> {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart =
      chartRef.current ?? echarts.getInstanceByDom(el) ?? echarts.init(el);
    chartRef.current = chart;
    chart.setOption(makeOption() as EChartsCoreOption, { notMerge: true });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // deps 由调用方（组件）作为完整依赖数组传入，闭包内 makeOption 捕获的变量已包含其中
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return ref;
}
