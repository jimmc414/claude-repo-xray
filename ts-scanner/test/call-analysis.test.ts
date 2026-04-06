import { describe, it, expect, beforeAll } from "vitest";
import * as path from "path";
import { analyzeCallGraph } from "../src/call-analysis.js";
import { analyzeFile } from "../src/ast-analysis.js";
import type { FileAnalysis, CallAnalysis } from "../src/types.js";

const CALLS_DIR = path.resolve(__dirname, "fixtures/minimal/src/calls");

describe("analyzeCallGraph", () => {
  const files = [
    path.join(CALLS_DIR, "service.ts"),
    path.join(CALLS_DIR, "handler.ts"),
    path.join(CALLS_DIR, "utils.ts"),
    path.join(CALLS_DIR, "index.ts"),
  ];
  const rootDir = path.resolve(CALLS_DIR, "../..");
  let fileResults: Record<string, FileAnalysis>;
  let result: CallAnalysis;

  beforeAll(() => {
    fileResults = {};
    for (const f of files) {
      fileResults[f] = analyzeFile(f);
    }
    result = analyzeCallGraph(fileResults, files, rootDir);
  });

  it("detects cross-module calls from handler to service", () => {
    // handler.ts imports { createUser, updateUser } from "./service"
    expect(result.cross_module["service.createUser"]).toBeDefined();
    expect(result.cross_module["service.createUser"].call_count).toBeGreaterThanOrEqual(1);
    expect(result.cross_module["service.updateUser"]).toBeDefined();
  });

  it("detects namespace calls (svc.deleteUser)", () => {
    // index.ts: import * as svc from "./service"; svc.deleteUser(1)
    expect(result.cross_module["service.deleteUser"]).toBeDefined();
    expect(result.cross_module["service.deleteUser"].call_count).toBeGreaterThanOrEqual(1);
  });

  it("detects namespace calls (svc.updateUser)", () => {
    // index.ts: svc.updateUser(2, "Bob")
    // Also called from handler.ts via named import
    expect(result.cross_module["service.updateUser"]).toBeDefined();
    expect(result.cross_module["service.updateUser"].call_count).toBeGreaterThanOrEqual(2);
  });

  it("detects named import call (handleCreate)", () => {
    // index.ts: import { handleCreate } from "./handler"; handleCreate("Alice")
    expect(result.cross_module["handler.handleCreate"]).toBeDefined();
    expect(result.cross_module["handler.handleCreate"].call_count).toBeGreaterThanOrEqual(1);
  });

  it("builds reverse lookup with impact ratings", () => {
    expect(result.reverse_lookup["service.createUser"]).toBeDefined();
    expect(result.reverse_lookup["service.createUser"].caller_count).toBeGreaterThanOrEqual(1);
    expect(["high", "medium", "low"]).toContain(
      result.reverse_lookup["service.createUser"].impact_rating
    );
  });

  it("populates most_called with correct shape", () => {
    expect(result.most_called.length).toBeGreaterThan(0);
    const first = result.most_called[0];
    expect(first).toHaveProperty("function");
    expect(first).toHaveProperty("call_sites");
    expect(first).toHaveProperty("modules");
    expect(typeof first.call_sites).toBe("number");
    expect(typeof first.modules).toBe("number");
  });

  it("populates most_callers with correct shape", () => {
    expect(result.most_callers.length).toBeGreaterThan(0);
    const first = result.most_callers[0];
    expect(first).toHaveProperty("function");
    expect(first).toHaveProperty("calls_made");
    expect(typeof first.calls_made).toBe("number");
  });

  it("identifies isolated functions", () => {
    // utils.formatName and utils.generateId are exported but never called cross-module
    expect(result.isolated_functions.some(f => f.includes("utils."))).toBe(true);
  });

  it("summary counts are consistent", () => {
    expect(result.summary.total_cross_module_calls).toBeGreaterThan(0);
    expect(result.summary.functions_with_cross_module_callers).toBe(
      Object.keys(result.cross_module).length
    );
    expect(result.summary.high_impact_functions).toBe(result.high_impact.length);
    expect(result.summary.isolated_functions).toBe(result.isolated_functions.length);
  });

  it("call sites include file and line info", () => {
    const entry = result.cross_module["service.createUser"];
    expect(entry.call_sites.length).toBeGreaterThan(0);
    const site = entry.call_sites[0];
    expect(site.file).toBeDefined();
    expect(site.line).toBeGreaterThan(0);
    expect(site.caller).toBeDefined();
  });
});

describe("analyzeCallGraph — empty input", () => {
  it("handles no files gracefully", () => {
    const result = analyzeCallGraph({}, [], "/tmp/empty");
    expect(result.summary.total_cross_module_calls).toBe(0);
    expect(result.most_called).toHaveLength(0);
    expect(result.most_callers).toHaveLength(0);
  });
});
