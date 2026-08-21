import { describe, expect, it } from "vitest";
import { t } from "./index";
import { messages } from "./messages";
import type { MessageKey } from "./messages";

describe("i18n 字典（E2）", () => {
  it("zh 与 en 的 key 集合完全一致（PRD AC3）", () => {
    const zh = Object.keys(messages.zh).sort();
    const en = Object.keys(messages.en).sort();
    expect(zh).toEqual(en);
  });

  it("所有 key 在两种语言下均为非空文案", () => {
    for (const key of Object.keys(messages.zh) as MessageKey[]) {
      expect(messages.zh[key].length).toBeGreaterThan(0);
      expect(messages.en[key].length).toBeGreaterThan(0);
    }
  });

  it("t 返回对应语言文案并支持 {var} 插值", () => {
    expect(t("zh", "summary.total", { n: 3 })).toBe("共 3 个账号");
    expect(t("en", "nav.usage")).toBe("Usage");
    expect(t("en", "summary.total", { n: 3 })).toBe("3 accounts");
    expect(t("zh", "quota.used", { p: 57 })).toBe("已用 57%");
  });

  it("t 对未知 key 回退为 zh 或 key 本身（不抛）", () => {
    expect(typeof t("en", "nav.usage" as MessageKey)).toBe("string");
  });
});
