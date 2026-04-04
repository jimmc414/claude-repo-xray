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
    expect(result.metadata.file_count).toBe(3);
    expect(result.metadata.generated_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("populates summary with correct file count", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    expect(result.summary.total_files).toBe(3);
    expect(result.summary.total_lines).toBeGreaterThan(0);
    expect(result.summary.total_tokens).toBeGreaterThan(0);
    expect(result.summary.total_functions).toBeGreaterThan(0);
    expect(result.summary.total_classes).toBeGreaterThan(0);
  });

  it("includes all fixture files in structure", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);
    const filePaths = Object.keys(result.structure.files);

    expect(filePaths.length).toBe(3);
    expect(filePaths.some((f: string) => f.endsWith("index.ts"))).toBe(true);
    expect(filePaths.some((f: string) => f.endsWith("user.service.ts"))).toBe(true);
    expect(filePaths.some((f: string) => f.endsWith("utils.ts"))).toBe(true);
  });

  it("aggregates classes across files", () => {
    const output = execSync(`node ${SCANNER_PATH} ${FIXTURE_PATH}`, { encoding: "utf-8" });
    const result = JSON.parse(output);

    // App (index.ts) + UserService (user.service.ts)
    expect(result.structure.classes.length).toBe(2);
    const classNames = result.structure.classes.map((c: { name: string }) => c.name);
    expect(classNames).toContain("App");
    expect(classNames).toContain("UserService");
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

  it("handles empty directory gracefully", () => {
    const output = execSync(`node ${SCANNER_PATH} /tmp`, { encoding: "utf-8" });
    const result = JSON.parse(output);
    expect(result.summary.total_files).toBe(0);
  });
});
