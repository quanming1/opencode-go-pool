import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";

const mocks = vi.hoisted(() => {
  const init = vi.fn();
  const getInstanceByDom = vi.fn();
  const setOption = vi.fn();
  const resize = vi.fn();
  const dispose = vi.fn();
  const chart = { setOption, resize, dispose };
  return { init, getInstanceByDom, setOption, resize, dispose, chart };
});

// hook 只用 echarts/core 的 init / getInstanceByDom（canvas 由真实 echarts 提供，
// jsdom 无 canvas，故 mock 掉整模块）
vi.mock("echarts/core", () => ({
  init: (el: unknown) => {
    mocks.init(el);
    return mocks.chart;
  },
  getInstanceByDom: (el: unknown) => mocks.getInstanceByDom(el),
}));

import { useEChart } from "./useEChart";

/** 渲染真实 <div> 并接住 useEChart 的 ref，否则 renderHook 下 ref.current 为 null。 */
function Harness({ n = 1 }: { n?: number }) {
  const ref = useEChart(() => ({ series: [{ type: "line", data: [n] }] }), [n]);
  return <div ref={ref} />;
}

describe("useEChart", () => {
  // 每个用例前清掉上一个用例的调用记录（保留 mock 定义），保证断言独立
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("首次挂载对元素 init 一次并 setOption", () => {
    render(<Harness />);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(mocks.setOption).toHaveBeenCalledTimes(1);
  });

  it("deps 变化复用实例，仅 setOption 更新、不重复 init", () => {
    const { rerender } = render(<Harness />);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(mocks.setOption).toHaveBeenCalledTimes(1);
    rerender(<Harness n={2} />);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(mocks.setOption).toHaveBeenCalledTimes(2);
  });

  it("窗口 resize 触发图表 resize", () => {
    render(<Harness />);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(mocks.resize).toHaveBeenCalledTimes(1);
  });

  it("卸载时销毁实例并移除 resize 监听", () => {
    const { unmount } = render(<Harness />);
    expect(mocks.dispose).not.toHaveBeenCalled();
    unmount();
    expect(mocks.dispose).toHaveBeenCalledTimes(1);
    // 卸载后 resize 事件不再触发图表 resize（监听已移除）
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(mocks.resize).toHaveBeenCalledTimes(0);
  });

  it("已有实例（getInstanceByDom 返回实例）时复用、不重复 init", () => {
    mocks.getInstanceByDom.mockReturnValue(mocks.chart);
    render(<Harness />);
    expect(mocks.init).toHaveBeenCalledTimes(0);
    expect(mocks.setOption).toHaveBeenCalledTimes(1);
  });
});
