import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const hintConsumers = [
  ["App", "src/App.tsx"],
  ["useHints", "src/queries/useHints.ts"],
  ["GameHintsPanel", "src/components/GameHintsPanel.tsx"],
] as const;

describe.each(hintConsumers)("%s hints API boundary", (_name, relativePath) => {
  it("routes hint requests through the shared HTTP client", () => {
    const source = readFileSync(resolve(process.cwd(), relativePath), "utf8");

    expect(source).not.toMatch(/\bfetch\s*\(\s*["']\/api\/hints["']/);
    expect(source).toContain("http.get<");
    expect(source).toMatch(/\bhttp\.get<[\s\S]*?>\s*\(\s*["']\/api\/hints["']/);
  });
});
