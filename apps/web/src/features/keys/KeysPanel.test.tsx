import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { KeysPanel } from "./KeysPanel";
import { createGatewayKey, fetchGatewayKeys, revokeGatewayKey } from "../../services/api";
import { I18nProvider } from "../../i18n";

vi.mock("../../services/api", () => ({
  fetchGatewayKeys: vi.fn(),
  createGatewayKey: vi.fn(),
  revokeGatewayKey: vi.fn(),
  rememberAdminKey: vi.fn((key: string) => {
    localStorage.setItem("ocp.gateway.admin.key", key);
  }),
}));

const mFetch = vi.mocked(fetchGatewayKeys);
const mCreate = vi.mocked(createGatewayKey);
const mRevoke = vi.mocked(revokeGatewayKey);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("KeysPanel", () => {
  it("空列表显示空态文案", async () => {
    mFetch.mockResolvedValue([]);
    render(<I18nProvider><KeysPanel /></I18nProvider>);
    await waitFor(() => expect(mFetch).toHaveBeenCalled());
    expect(screen.getByText(/暂无 key/)).toBeDefined();
  });

  it("key 列表渲染：label / 状态徽章 / 吊销按钮", async () => {
    mFetch.mockResolvedValue([
      { id: 1, label: "ftre", created_at: "2026-08-20T10:00:00", revoked_at: null },
      { id: 2, label: "old", created_at: "2026-08-19T10:00:00", revoked_at: "2026-08-20T09:00:00" },
    ]);
    render(<I18nProvider><KeysPanel /></I18nProvider>);
    await waitFor(() => expect(screen.getByText("ftre")).toBeDefined());
    expect(screen.getByText("有效")).toBeDefined();
    expect(screen.getByText("已吊销")).toBeDefined();
    expect(screen.getByText("已有 Key（2）")).toBeDefined();
  });

  it("生成 key：明文一次性展示并可复制", async () => {
    mFetch.mockResolvedValue([]);
    mCreate.mockResolvedValue({
      id: 1,
      label: "ftre",
      key: "gk-abc123",
      created_at: "2026-08-20T10:00:00",
    });
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
    Object.assign(navigator, { clipboard });

    render(<I18nProvider><KeysPanel /></I18nProvider>);
    fireEvent.change(screen.getByTestId("key-label-input"), { target: { value: "ftre" } });
    fireEvent.click(screen.getByTestId("key-create-btn"));

    await waitFor(() => expect(mCreate).toHaveBeenCalledWith("ftre"));
    await waitFor(() => expect(screen.getByTestId("key-once")).toBeDefined());
    expect(screen.getByText("gk-abc123")).toBeDefined();

    fireEvent.click(screen.getByText("复制"));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith("gk-abc123"));
    await waitFor(() => expect(screen.getByText("已复制")).toBeDefined());
  });

  it("吊销需二次确认", async () => {
    mFetch.mockResolvedValue([
      { id: 1, label: "ftre", created_at: "2026-08-20T10:00:00", revoked_at: null },
    ]);
    render(<I18nProvider><KeysPanel /></I18nProvider>);
    await waitFor(() => expect(screen.getByText("ftre")).toBeDefined());

    fireEvent.click(screen.getByText("吊销"));
    expect(screen.getByText("确认吊销？")).toBeDefined();
    expect(mRevoke).not.toHaveBeenCalled();

    mRevoke.mockResolvedValue({ ok: true });
    fireEvent.click(screen.getByText("确认"));
    await waitFor(() => expect(mRevoke).toHaveBeenCalledWith(1));
  });

  it("401 时显示解锁入口，输入有效 key 后恢复", async () => {
    localStorage.removeItem("ocp.gateway.admin.key");
    mFetch.mockRejectedValueOnce(new Error("请求失败: 401"));
    mFetch.mockResolvedValueOnce([
      { id: 1, label: "ftre", created_at: "2026-08-20T10:00:00", revoked_at: null },
    ]);

    render(<I18nProvider><KeysPanel /></I18nProvider>);
    await waitFor(() => expect(screen.getByTestId("key-unlock")).toBeDefined());

    fireEvent.change(screen.getByTestId("unlock-input"), {
      target: { value: "gk-saved-key" },
    });
    fireEvent.click(screen.getByTestId("unlock-btn"));
    await waitFor(() => expect(screen.getByText("ftre")).toBeDefined());
    expect(localStorage.getItem("ocp.gateway.admin.key")).toBe("gk-saved-key");
    expect(screen.queryByTestId("key-unlock")).toBeNull();
  });
});
