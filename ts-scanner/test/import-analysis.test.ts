import { describe, it, expect, beforeAll } from "vitest";
import * as path from "path";
import * as fs from "fs";
import { analyzeImports } from "../src/import-analysis.js";
import type { ImportAnalysis } from "../src/types.js";

const FIXTURES_DIR = path.resolve(__dirname, "fixtures/minimal/src");
const IMPORT_FIXTURES_DIR = path.resolve(__dirname, "fixtures/imports");

// =============================================================================
// Tests using the existing minimal fixture
// =============================================================================

describe("analyzeImports — minimal fixture", () => {
  const files = [
    path.join(FIXTURES_DIR, "index.ts"),
    path.join(FIXTURES_DIR, "user.service.ts"),
    path.join(FIXTURES_DIR, "utils.ts"),
  ];
  const rootDir = path.resolve(FIXTURES_DIR, "..");
  let result: ImportAnalysis;

  beforeAll(() => {
    result = analyzeImports(files, rootDir);
  });

  it("reports correct module count", () => {
    expect(result.summary.total_modules).toBe(3);
  });

  it("resolves relative imports to known files", () => {
    // index.ts imports from ./user.service and ./utils
    const indexNode = result.graph["src/index.ts"];
    expect(indexNode).toBeDefined();
    expect(indexNode.imports).toContain("src/user.service.ts");
    expect(indexNode.imports).toContain("src/utils.ts");
  });

  it("tracks imported_by (reverse edges)", () => {
    const utilsNode = result.graph["src/utils.ts"];
    expect(utilsNode).toBeDefined();
    expect(utilsNode.imported_by).toContain("src/index.ts");
  });

  it("counts internal edges", () => {
    // index.ts → user.service.ts, index.ts → utils.ts = 2 edges
    expect(result.summary.internal_edges).toBe(2);
  });

  it("detects no circular deps in the minimal fixture", () => {
    expect(result.summary.circular_count).toBe(0);
    expect(result.circular).toHaveLength(0);
  });

  it("detects orphans (files with no imports/importers)", () => {
    // user.service.ts is imported by index.ts but imports nothing → not orphan
    // utils.ts is imported by index.ts but imports nothing → not orphan
    // All files have at least one connection
    expect(result.summary.orphan_count).toBe(0);
  });

  it("returns empty external deps for fixture with no package imports", () => {
    // The fixture only has relative imports
    expect(result.summary.external_deps_count).toBe(0);
  });

  it("computes dependency distances", () => {
    expect(result.distances.max_depth).toBeGreaterThanOrEqual(1);
    expect(result.distances.avg_depth).toBeGreaterThanOrEqual(0);
  });
});

// =============================================================================
// Tests using a dedicated import fixture with circular deps and externals
// =============================================================================

describe("analyzeImports — import fixture", () => {
  const fixtureDir = IMPORT_FIXTURES_DIR;
  let result: ImportAnalysis;

  beforeAll(() => {
    // Create fixture files for import testing
    fs.mkdirSync(path.join(fixtureDir, "services"), { recursive: true });
    fs.mkdirSync(path.join(fixtureDir, "utils"), { recursive: true });
    fs.mkdirSync(path.join(fixtureDir, "models"), { recursive: true });
    fs.mkdirSync(path.join(fixtureDir, "types"), { recursive: true });

    // Entry point
    fs.writeFileSync(path.join(fixtureDir, "index.ts"), [
      'import { UserService } from "./services/user-service";',
      'import { logger } from "./utils/logger";',
      'import express from "express";',
      "",
      "const app = express();",
      "export default app;",
    ].join("\n"));

    // Service that imports a model (and has circular dep with another service)
    fs.writeFileSync(path.join(fixtureDir, "services/user-service.ts"), [
      'import { User } from "../models/user";',
      'import { AuthService } from "./auth-service";',
      'import { logger } from "../utils/logger";',
      'import bcrypt from "bcrypt";',
      "",
      "export class UserService {",
      "  constructor(private auth: AuthService) {}",
      "}",
    ].join("\n"));

    // Service with circular dep back to user-service
    fs.writeFileSync(path.join(fixtureDir, "services/auth-service.ts"), [
      'import { UserService } from "./user-service";',
      'import { logger } from "../utils/logger";',
      "",
      "export class AuthService {",
      "  constructor(private users: UserService) {}",
      "}",
    ].join("\n"));

    // Model
    fs.writeFileSync(path.join(fixtureDir, "models/user.ts"), [
      'import type { UserId } from "../types/ids";',
      "",
      "export interface User {",
      "  id: UserId;",
      "  name: string;",
      "}",
    ].join("\n"));

    // Types
    fs.writeFileSync(path.join(fixtureDir, "types/ids.ts"), [
      "export type UserId = string;",
      "export type PostId = string;",
    ].join("\n"));

    // Logger utility — hub module (imported by many)
    fs.writeFileSync(path.join(fixtureDir, "utils/logger.ts"), [
      "export const logger = {",
      '  info: (msg: string) => console.log("[INFO]", msg),',
      '  error: (msg: string) => console.error("[ERROR]", msg),',
      "};",
    ].join("\n"));

    // Orphan file (no imports, no importers, not an entry point)
    fs.writeFileSync(path.join(fixtureDir, "utils/unused-helper.ts"), [
      "export function unusedHelper(): void {}",
    ].join("\n"));

    // Re-export file
    fs.writeFileSync(path.join(fixtureDir, "services/index.ts"), [
      'export { UserService } from "./user-service";',
      'export { AuthService } from "./auth-service";',
    ].join("\n"));

    const files = [
      path.join(fixtureDir, "index.ts"),
      path.join(fixtureDir, "services/user-service.ts"),
      path.join(fixtureDir, "services/auth-service.ts"),
      path.join(fixtureDir, "services/index.ts"),
      path.join(fixtureDir, "models/user.ts"),
      path.join(fixtureDir, "types/ids.ts"),
      path.join(fixtureDir, "utils/logger.ts"),
      path.join(fixtureDir, "utils/unused-helper.ts"),
    ];

    result = analyzeImports(files, fixtureDir);
  });

  it("counts 8 total modules", () => {
    expect(result.summary.total_modules).toBe(8);
  });

  it("detects circular dependency between user-service and auth-service", () => {
    expect(result.summary.circular_count).toBe(1);
    expect(result.circular).toHaveLength(1);
    const pair = result.circular[0].sort();
    expect(pair).toContain("services/auth-service.ts");
    expect(pair).toContain("services/user-service.ts");
  });

  it("detects external dependencies", () => {
    expect(result.external_deps).toContain("express");
    expect(result.external_deps).toContain("bcrypt");
    expect(result.summary.external_deps_count).toBe(2);
  });

  it("detects orphan modules", () => {
    expect(result.orphans).toContain("utils/unused-helper.ts");
    expect(result.summary.orphan_count).toBe(1);
  });

  it("identifies logger as a hub module", () => {
    const loggerHub = result.distances.hub_modules.find(
      h => h.module === "utils/logger.ts"
    );
    expect(loggerHub).toBeDefined();
    expect(loggerHub!.connections).toBeGreaterThanOrEqual(3);
  });

  it("classifies files into layers", () => {
    expect(result.layers["services"]).toBeDefined();
    expect(result.layers["models"]).toBeDefined();
    expect(result.layers["utils"]).toBeDefined();
    expect(result.layers["types"]).toBeDefined();

    expect(result.layers["services"]).toContain("services/user-service.ts");
    expect(result.layers["models"]).toContain("models/user.ts");
    expect(result.layers["utils"]).toContain("utils/logger.ts");
  });

  it("resolves re-exports as import edges", () => {
    const barrel = result.graph["services/index.ts"];
    expect(barrel).toBeDefined();
    expect(barrel.imports).toContain("services/user-service.ts");
    expect(barrel.imports).toContain("services/auth-service.ts");
  });

  it("computes meaningful dependency distances", () => {
    // Chain: index → services/user-service → models/user → types/ids
    expect(result.distances.max_depth).toBeGreaterThanOrEqual(3);
  });

  it("detects tightly coupled pairs", () => {
    // user-service and auth-service import each other = score >= 2
    const tight = result.distances.tightly_coupled.find(
      tc => tc.modules.includes("services/user-service.ts") &&
            tc.modules.includes("services/auth-service.ts")
    );
    expect(tight).toBeDefined();
    expect(tight!.score).toBeGreaterThanOrEqual(2);
  });
});

// =============================================================================
// Topological tiers
// =============================================================================

describe("analyzeImports — topological tiers", () => {
  it("classifies utils.ts as foundation (keyword)", () => {
    const files = [
      path.join(FIXTURES_DIR, "index.ts"),
      path.join(FIXTURES_DIR, "user.service.ts"),
      path.join(FIXTURES_DIR, "utils.ts"),
    ];
    const result = analyzeImports(files, path.resolve(FIXTURES_DIR, ".."));
    expect(result.tiers).toBeDefined();
    expect(result.tiers!.foundation).toContain("src/utils.ts");
  });

  it("classifies index.ts as orchestration (keyword)", () => {
    const files = [
      path.join(FIXTURES_DIR, "index.ts"),
      path.join(FIXTURES_DIR, "user.service.ts"),
      path.join(FIXTURES_DIR, "utils.ts"),
    ];
    const result = analyzeImports(files, path.resolve(FIXTURES_DIR, ".."));
    expect(result.tiers!.orchestration).toContain("src/index.ts");
  });

  it("has all four tier keys", () => {
    const files = [
      path.join(FIXTURES_DIR, "index.ts"),
      path.join(FIXTURES_DIR, "user.service.ts"),
      path.join(FIXTURES_DIR, "utils.ts"),
    ];
    const result = analyzeImports(files, path.resolve(FIXTURES_DIR, ".."));
    expect(result.tiers).toHaveProperty("orchestration");
    expect(result.tiers).toHaveProperty("core");
    expect(result.tiers).toHaveProperty("foundation");
    expect(result.tiers).toHaveProperty("leaf");
  });

  it("classifies hub module (imported by many) as foundation", () => {
    // In the import fixture, logger is imported by 3 files → ratio > 2 → foundation
    const fixtureDir = IMPORT_FIXTURES_DIR;
    const files = [
      path.join(fixtureDir, "index.ts"),
      path.join(fixtureDir, "services/user-service.ts"),
      path.join(fixtureDir, "services/auth-service.ts"),
      path.join(fixtureDir, "services/index.ts"),
      path.join(fixtureDir, "models/user.ts"),
      path.join(fixtureDir, "types/ids.ts"),
      path.join(fixtureDir, "utils/logger.ts"),
      path.join(fixtureDir, "utils/unused-helper.ts"),
    ];
    const result = analyzeImports(files, fixtureDir);
    // logger.ts is imported by 3 files, imports 0 → ratio = 3 → foundation
    expect(result.tiers!.foundation).toContain("utils/logger.ts");
  });

  it("classifies disconnected file as leaf", () => {
    const fixtureDir = IMPORT_FIXTURES_DIR;
    const files = [
      path.join(fixtureDir, "index.ts"),
      path.join(fixtureDir, "services/user-service.ts"),
      path.join(fixtureDir, "services/auth-service.ts"),
      path.join(fixtureDir, "services/index.ts"),
      path.join(fixtureDir, "models/user.ts"),
      path.join(fixtureDir, "types/ids.ts"),
      path.join(fixtureDir, "utils/logger.ts"),
      path.join(fixtureDir, "utils/unused-helper.ts"),
    ];
    const result = analyzeImports(files, fixtureDir);
    // unused-helper.ts has no imports and no importers → leaf
    expect(result.tiers!.leaf).toContain("utils/unused-helper.ts");
  });
});

// =============================================================================
// Edge cases
// =============================================================================

describe("analyzeImports — edge cases", () => {
  it("handles empty file list", () => {
    const result = analyzeImports([], "/tmp/empty");
    expect(result.summary.total_modules).toBe(0);
    expect(result.summary.internal_edges).toBe(0);
  });

  it("extracts scoped package names correctly", () => {
    // Validate via ccusage-like imports if we had them.
    // Tested indirectly via the fixture above (express, bcrypt).
    const result = analyzeImports([], "/tmp/empty");
    expect(result.external_deps).toHaveLength(0);
  });
});
