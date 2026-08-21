/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { darkTokens, lightTokens, chartColors, colorTokens, type ColorTokens } from "./tokens";

/** 解析 index.css 中某个块（:root / html[data-theme="dark"]）内的 --color-* 定义。 */
function parseCssColorBlock(css: string, block: ":root" | 'html[data-theme="dark"]'): Partial<ColorTokens> {
  const escaped = block.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "s");
  const match = css.match(re);
  if (!match) throw new Error(`index.css 未找到颜色块：${block}`);
  const out: Partial<ColorTokens> = {};
  for (const [, key, value] of match[1].matchAll(/--color-([a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,8})/g)) {
    out[key as keyof ColorTokens] = value;
  }
  return out;
}



const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf-8");

describe("theme/tokens 与 index.css 一致性（E3 防双源漂移）", () => {
  const expectedKeys: (keyof ColorTokens)[] = [
    "bg",
    "bg-subtle",
    "text",
    "text-secondary",
    "border",
    "accent",
    "ok",
    "warn",
    "danger",
  ];

  it("lightTokens 与 :root 的 9 个 --color-* 逐条一致", () => {
    const fromCss = parseCssColorBlock(css, ":root");
    for (const key of expectedKeys) {
      expect(fromCss[key], `:root 缺少 --color-${key}`).toBeDefined();
      expect(lightTokens[key]).toBe(fromCss[key]);
    }
  });

  it("darkTokens 与 html[data-theme=dark] 的 9 个 --color-* 逐条一致", () => {
    const fromCss = parseCssColorBlock(css, 'html[data-theme="dark"]');
    for (const key of expectedKeys) {
      expect(fromCss[key], `dark 块缺少 --color-${key}`).toBeDefined();
      expect(darkTokens[key]).toBe(fromCss[key]);
    }
  });

  it("light/dark 两组 token 键集合一致（无漏加/多出）", () => {
    expect(Object.keys(lightTokens).sort()).toEqual([...expectedKeys].sort());
    expect(Object.keys(darkTokens).sort()).toEqual([...expectedKeys].sort());
  });
});

describe("chartColors 派生色板", () => {
  it("light 取自 lightTokens（label 映射 text-secondary）", () => {
    const c = chartColors("light");
    expect(c).toEqual({
      accent: lightTokens.accent,
      ok: lightTokens.ok,
      warn: lightTokens.warn,
      danger: lightTokens.danger,
      border: lightTokens.border,
      label: lightTokens["text-secondary"],
    });
  });

  it("dark 取自 darkTokens（label 映射 text-secondary）", () => {
    const c = chartColors("dark");
    expect(c).toEqual({
      accent: darkTokens.accent,
      ok: darkTokens.ok,
      warn: darkTokens.warn,
      danger: darkTokens.danger,
      border: darkTokens.border,
      label: darkTokens["text-secondary"],
    });
  });

  it("colorTokens 按主题返回对应集", () => {
    expect(colorTokens("light")).toBe(lightTokens);
    expect(colorTokens("dark")).toBe(darkTokens);
  });
});
