import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useAccountPolling } from "./useAccountPolling";
import type { PoolAccount } from "../../types/pool";

const sample: PoolAccount[] = [
  {
    id: "a1",
    name: "账号A",
    status: "healthy",
    cooldown_until: null,
    cooldown_seconds_remaining: null,
    last_error: null,
    error_count: 0,
    consecutive_failures: 0,
    enabled: true,
  },
];

describe("useAccountPolling", () => {
  it("调用 fetch 并更新状态且不再 loading", async () => {
    const fetchFn = vi.fn(async () => sample);
    const { result, unmount } = renderHook(() => useAccountPolling(50, fetchFn));
    await waitFor(() => expect(fetchFn).toHaveBeenCalled());
    await waitFor(() => expect(result.current.accounts).toEqual(sample));
    expect(result.current.loading).toBe(false);
    unmount();
  });

  it("fetch 失败时置 error", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("boom");
    });
    const { result, unmount } = renderHook(() => useAccountPolling(50, fetchFn));
    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.loading).toBe(false);
    unmount();
  });
});
