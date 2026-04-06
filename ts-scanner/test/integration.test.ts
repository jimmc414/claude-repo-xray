import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import * as path from "path";

const SCANNER_PATH = path.resolve(__dirname, "../dist/index.js");
const FIXTURE_PATH = path.resolve(__dirname, "fixtures/minimal");

describe("integration", () => {
  it("produces valid JSON output", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, {
      encoding: "utf-8",
      timeout: 30000,
    });
    const result = JSON.parse(output);
    expect(result).toBeDefined();
  });

  it("has all required top-level keys", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.metadata).toBeDefined();
    expect(result.summary).toBeDefined();
    expect(result.structure).toBeDefined();
    expect(result.complexity).toBeDefined();
    expect(result.types).toBeDefined();
    expect(result.decorators).toBeDefined();
    expect(result.async_patterns).toBeDefined();
  });

  it("populates metadata correctly", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.metadata.tool_version).toBe("0.1.0");
    expect(result.metadata.language).toBe("typescript");
    expect(result.metadata.parser_tier).toBe("syntax");
    expect(result.metadata.file_count).toBe(10);
    expect(result.metadata.generated_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("populates summary with correct file count", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.summary.total_files).toBe(10);
    expect(result.summary.total_lines).toBeGreaterThan(0);
    expect(result.summary.total_tokens).toBeGreaterThan(0);
    expect(result.summary.total_functions).toBeGreaterThan(0);
    expect(result.summary.total_classes).toBeGreaterThan(0);
  });

  it("includes all fixture files in structure", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);
    const filePaths = Object.keys(result.structure.files);

    expect(filePaths.length).toBe(10);
    expect(filePaths.some((f: string) => f.endsWith("index.ts"))).toBe(true);
    expect(filePaths.some((f: string) => f.endsWith("user.service.ts"))).toBe(true);
    expect(filePaths.some((f: string) => f.endsWith("utils.ts"))).toBe(true);
    expect(filePaths.some((f: string) => f.endsWith("behavioral.ts"))).toBe(true);
  });

  it("aggregates classes across files", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    // App (index.ts) + UserService (user.service.ts) + ConfigService (behavioral.ts) + StatefulService (mutable-state.ts)
    expect(result.structure.classes.length).toBe(4);
    const classNames = result.structure.classes.map((c: { name: string }) => c.name);
    expect(classNames).toContain("App");
    expect(classNames).toContain("UserService");
    expect(classNames).toContain("ConfigService");
    expect(classNames).toContain("StatefulService");
  });

  it("aggregates functions across files", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    // bootstrap, getVersion (index.ts) + formatName, isValidEmail, retry, identity, clamp (utils.ts)
    expect(result.structure.functions.length).toBeGreaterThanOrEqual(5);
  });

  it("calculates complexity hotspots", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.complexity.hotspots.length).toBeGreaterThan(0);
    // Hotspots should be sorted by complexity descending
    for (let i = 1; i < result.complexity.hotspots.length; i++) {
      expect(result.complexity.hotspots[i - 1].complexity)
        .toBeGreaterThanOrEqual(result.complexity.hotspots[i].complexity);
    }
  });

  it("reports type coverage", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.types.total_functions).toBeGreaterThan(0);
    expect(result.types.typed_functions).toBeGreaterThan(0);
    expect(result.types.coverage).toBeGreaterThan(0);
  });

  it("exits with code 0 on success", () => {
    // execSync throws on non-zero exit
    expect(() => {
      execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    }).not.toThrow();
  });

  it("exits with code 1 when no target provided", () => {
    expect(() => {
      execSync(`node ${SCANNER_PATH}`, { encoding: "utf-8" });
    }).toThrow();
  });

  it("aggregates side effects by type", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.side_effects).toBeDefined();
    expect(result.side_effects.by_type).toBeDefined();
    expect(Object.keys(result.side_effects.by_type).length).toBeGreaterThan(0);
  });

  it("includes test analysis", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.tests).toBeDefined();
    expect(result.tests.test_file_count).toBeGreaterThanOrEqual(0);
    expect(result.tests.test_function_count).toBeGreaterThanOrEqual(0);
  });

  it("detects security concerns", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(Object.keys(result.security_concerns).length).toBeGreaterThan(0);
  });

  it("detects deprecation markers", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.deprecation_markers.length).toBeGreaterThan(0);
  });

  it("includes call analysis", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.calls).toBeDefined();
    expect(result.calls.summary).toBeDefined();
    expect(result.calls.summary.total_cross_module_calls).toBeGreaterThanOrEqual(0);
    expect(result.calls.most_called).toBeDefined();
    expect(result.calls.most_callers).toBeDefined();
    expect(result.calls.isolated_functions).toBeDefined();
  });

  it("includes topological tiers in imports", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.imports.tiers).toBeDefined();
    expect(result.imports.tiers).toHaveProperty("foundation");
    expect(result.imports.tiers).toHaveProperty("core");
    expect(result.imports.tiers).toHaveProperty("orchestration");
    expect(result.imports.tiers).toHaveProperty("leaf");
  });

  it("generates logic maps for hotspots", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.logic_maps).toBeDefined();
    expect(Array.isArray(result.logic_maps)).toBe(true);
    expect(result.logic_maps.length).toBeGreaterThan(0);

    const map = result.logic_maps[0];
    expect(map.method).toBeDefined();
    expect(map.file).toBeDefined();
    expect(map.line).toBeGreaterThan(0);
    expect(map.complexity).toBeGreaterThan(0);
    expect(Array.isArray(map.flow)).toBe(true);
    expect(map.flow.length).toBeGreaterThan(0);
    expect(Array.isArray(map.side_effects)).toBe(true);
    expect(Array.isArray(map.state_mutations)).toBe(true);
    expect(Array.isArray(map.conditions)).toBe(true);
    expect(typeof map.heuristic).toBe("string");
  });

  it("detects shared mutable state in files", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    // mutable-state.ts has module-level let declarations
    const files = result.structure.files;
    const mutableFile = Object.entries(files).find(
      ([k]) => k.endsWith("mutable-state.ts")
    );
    expect(mutableFile).toBeDefined();
    const [, fileData] = mutableFile as [string, { shared_mutable_state?: Array<{ name: string }> }];
    expect(fileData.shared_mutable_state).toBeDefined();
    expect(fileData.shared_mutable_state!.length).toBeGreaterThan(0);
  });

  it("handles empty directory gracefully", () => {
    const emptyDir = path.join(FIXTURE_PATH, "..", "empty-test-dir");
    const fs = require("fs");
    fs.mkdirSync(emptyDir, { recursive: true });
    try {
      const output = execSync(`node ${SCANNER_PATH} ${emptyDir}`, { encoding: "utf-8" });
      const result = JSON.parse(output);
      expect(result.summary.total_files).toBe(0);
    } finally {
      fs.rmSync(emptyDir, { recursive: true, force: true });
    }
  });
});
