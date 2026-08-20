import { describe, expect, it } from "vitest";
import { quotaTone, resetsInText } from "./quotaFormat";

describe("resetsInText", () => {
  it("处理未知与即将重置", () => {
    expect(resetsInText(null)).toBe("-");
    expect(resetsInText(0)).toBe("即将重置");
    expect(resetsInText(30)).toBe("即将重置");
  });

  it("按分钟、小时和天显示倒计时", () => {
    expect(resetsInText(57 * 60)).toBe("57 分钟");
    expect(resetsInText(3 * 3600 + 18 * 60)).toBe("3 小时 18 分钟");
    expect(resetsInText(30 * 86400)).toBe("30 天 0 小时");
    expect(resetsInText(3 * 86400 + 18 * 3600 + 59)).toBe("3 天 18 小时");
  });
});

describe("quotaTone", () => {
  it("限额或 100% 为红色，80% 以上为橙色", () => {
    expect(quotaTone(100, "ok")).toBe("danger");
    expect(quotaTone(50, "rate-limited")).toBe("danger");
    expect(quotaTone(80, "ok")).toBe("warn");
    expect(quotaTone(79, "ok")).toBe("ok");
  });
});
