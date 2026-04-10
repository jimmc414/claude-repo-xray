import { describe, it, expect } from "vitest";
import * as path from "path";
import { analyzeFile } from "../src/ast-analysis.js";
import { generateLogicMaps } from "../src/logic-maps.js";
import type { FileAnalysis } from "../src/types.js";

const FIXTURES = path.resolve(__dirname, "fixtures/minimal/src");
const TARGET_FILE = path.join(FIXTURES, "logic-map-target.ts");

describe("generateLogicMaps", () => {
  const fileResults: Record<string, FileAnalysis> = {
    [TARGET_FILE]: analyzeFile(TARGET_FILE),
  };

  it("generates a logic map for complex function", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);

    expect(maps.length).toBe(1);
    expect(maps[0].method).toBe("processItems");
    expect(maps[0].file).toBe(TARGET_FILE);
    expect(maps[0].complexity).toBe(5);
    expect(maps[0].line).toBeGreaterThan(0);
  });

  it("flow lines include control flow markers", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);
    const flow = maps[0].flow;

    // Should contain if/else, for-of, try, catch, return
    expect(flow.some(l => l.includes("->") && l.includes("?"))).toBe(true);
    expect(flow.some(l => l.includes("*") && l.includes("for"))).toBe(true);
    expect(flow.some(l => l.includes("try:"))).toBe(true);
    expect(flow.some(l => l.includes("! catch"))).toBe(true);
    expect(flow.some(l => l.includes("Return"))).toBe(true);
  });

  it("detects side effects", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);

    // console.error is a logging side effect
    expect(maps[0].side_effects.length).toBeGreaterThan(0);
    expect(maps[0].side_effects.some(s => s.includes("logging"))).toBe(true);
  });

  it("generates heuristic summary", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);

    expect(maps[0].heuristic).toContain("branch");
    expect(maps[0].heuristic.length).toBeGreaterThan(0);
  });

  it("extracts docstring", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);

    expect(maps[0].docstring).toContain("Process items");
  });

  it("returns empty array for no hotspots", () => {
    const maps = generateLogicMaps([], fileResults, 10);
    expect(maps).toEqual([]);
  });

  it("respects maxMaps limit", () => {
    const hotspots = [
      { file: TARGET_FILE, function: "processItems", complexity: 5 },
      { file: TARGET_FILE, function: "simpleFunction", complexity: 1 },
    ];
    const maps = generateLogicMaps(hotspots, fileResults, 1);
    expect(maps.length).toBe(1);
  });

  it("deduplicates by file:function", () => {
    const hotspots = [
      { file: TARGET_FILE, function: "processItems", complexity: 5 },
      { file: TARGET_FILE, function: "processItems", complexity: 5 },
    ];
    const maps = generateLogicMaps(hotspots, fileResults, 10);
    expect(maps.length).toBe(1);
  });

  it("collects conditions", () => {
    const hotspots = [{ file: TARGET_FILE, function: "processItems", complexity: 5 }];
    const maps = generateLogicMaps(hotspots, fileResults, 10);

    expect(maps[0].conditions.length).toBeGreaterThan(0);
  });

  describe("ternary and short-circuit patterns", () => {
    it("generates flow entries for ternary expressions", () => {
      const hotspots = [{ file: TARGET_FILE, function: "renderComponent", complexity: 3 }];
      const maps = generateLogicMaps(hotspots, fileResults, 10);

      expect(maps.length).toBe(1);
      const flow = maps[0].flow;
      expect(flow.some(l => l.includes("THEN:"))).toBe(true);
      expect(flow.some(l => l.includes("ELSE:"))).toBe(true);
    });

    it("generates flow entries for && short-circuit", () => {
      const hotspots = [{ file: TARGET_FILE, function: "renderComponent", complexity: 3 }];
      const maps = generateLogicMaps(hotspots, fileResults, 10);

      const flow = maps[0].flow;
      expect(flow.some(l => l.includes("&&"))).toBe(true);
    });

    it("populates conditions for ternary/short-circuit", () => {
      const hotspots = [{ file: TARGET_FILE, function: "renderComponent", complexity: 3 }];
      const maps = generateLogicMaps(hotspots, fileResults, 10);

      expect(maps[0].conditions.length).toBeGreaterThanOrEqual(2);
    });
  });
});
