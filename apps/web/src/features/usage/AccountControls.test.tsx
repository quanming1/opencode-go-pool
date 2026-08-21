import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AccountControls } from "./AccountControls";
import { clearAccount, disableAccount, enableAccount } from "../../services/api";
import type { PoolAccount } from "../../types/pool";
import { I18nProvider } from "../../i18n";

vi.mock("../../services/api", () => ({
  clearAccount: vi.fn(),
  disableAccount: vi.fn(),
  enableAccount: vi.fn(),
}));

const mClear = vi.mocked(clearAccount);
const mDisable = vi.mocked(disableAccount);
const mEnable = vi.mocked(enableAccount);

function account(status: PoolAccount["status"], enabled = true): PoolAccount {
  return {
    id: "a1",
    name: "A",
    status,
    cooldown_until: null,
    cooldown_seconds_remaining: null,
    last_error: null,
    error_count: 0,
    consecutive_failures: 0,
    enabled,
  };
}

describe("AccountControls", () => {
  it("cooldown 账号显示清除冷却与禁用按钮", () => {
    const onChanged = vi.fn();
    render(<I18nProvider><AccountControls account={account("cooldown")} onChanged={onChanged} /></I18nProvider>);
    expect(screen.getByText("清除冷却")).toBeDefined();
    expect(screen.getByText("禁用")).toBeDefined();
    expect(screen.queryByText("启用")).toBeNull();
  });

  it("点击清除冷却调用 API 并触发刷新", async () => {
    mClear.mockResolvedValue({ ok: true });
    const onChanged = vi.fn();
    render(<I18nProvider><AccountControls account={account("cooldown")} onChanged={onChanged} /></I18nProvider>);
    fireEvent.click(screen.getByText("清除冷却"));
    await waitFor(() => expect(mClear).toHaveBeenCalledWith("a1"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("禁用账号显示启用按钮", () => {
    render(<I18nProvider><AccountControls account={account("disabled", false)} onChanged={vi.fn()} /></I18nProvider>);
    expect(screen.getByText("启用")).toBeDefined();
    expect(screen.queryByText("清除冷却")).toBeNull();
  });

  it("启用按钮调用 enableAccount", async () => {
    mEnable.mockResolvedValue({ ok: true });
    render(<I18nProvider><AccountControls account={account("disabled", false)} onChanged={vi.fn()} /></I18nProvider>);
    fireEvent.click(screen.getByText("启用"));
    await waitFor(() => expect(mEnable).toHaveBeenCalledWith("a1"));
  });

  it("API 失败显示错误", async () => {
    mDisable.mockRejectedValue(new Error("boom"));
    render(<I18nProvider><AccountControls account={account("healthy")} onChanged={vi.fn()} /></I18nProvider>);
    fireEvent.click(screen.getByText("禁用"));
    await waitFor(() => expect(screen.getByText(/boom/)).toBeDefined());
  });
});
