import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { analyzeConfig } from "../src/config-analysis.js";

const TMP_DIR = path.resolve(__dirname, ".tmp-config-test");

beforeAll(() => {
  fs.mkdirSync(TMP_DIR, { recursive: true });
});

afterAll(() => {
  fs.rmSync(TMP_DIR, { recursive: true, force: true });
});

describe("analyzeConfig", () => {
  describe("tsconfig.json", () => {
    it("extracts strict flags from tsconfig", () => {
      const dir = path.join(TMP_DIR, "ts-strict");
      fs.mkdirSync(dir, { recursive: true });
      const tsconfigPath = path.join(dir, "tsconfig.json");
      fs.writeFileSync(tsconfigPath, JSON.stringify({
        compilerOptions: {
          strict: true,
          noImplicitAny: true,
          noUnusedLocals: false,
          target: "ES2022",
          module: "Node16",
        },
      }));

      const result = analyzeConfig(dir, tsconfigPath);
      expect(result.typescript).not.toBeNull();
      expect(result.typescript!.strict).toBe(true);
      expect(result.typescript!.flags["strict"]).toBe(true);
      expect(result.typescript!.flags["noImplicitAny"]).toBe(true);
      expect(result.typescript!.flags["noUnusedLocals"]).toBe(false);
      expect(result.typescript!.flags["target"]).toBe("ES2022");
      expect(result.typescript!.config_file).toBe("tsconfig.json");
    });

    it("returns null typescript when no tsconfig path", () => {
      const result = analyzeConfig(TMP_DIR, null);
      expect(result.typescript).toBeNull();
    });

    it("returns null typescript for malformed tsconfig", () => {
      const dir = path.join(TMP_DIR, "ts-bad");
      fs.mkdirSync(dir, { recursive: true });
      const tsconfigPath = path.join(dir, "tsconfig.json");
      fs.writeFileSync(tsconfigPath, "not valid json {{{");

      const result = analyzeConfig(dir, tsconfigPath);
      expect(result.typescript).toBeNull();
    });
  });

  describe("eslint detection", () => {
    it("detects eslint.config.js", () => {
      const dir = path.join(TMP_DIR, "eslint-flat");
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "eslint.config.js"), "export default {};");

      const result = analyzeConfig(dir, null);
      expect(result.eslint).not.toBeNull();
      expect(result.eslint!.config_file).toBe("eslint.config.js");
    });

    it("detects .eslintrc.json with framework", () => {
      const dir = path.join(TMP_DIR, "eslint-json");
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, ".eslintrc.json"), JSON.stringify({
        extends: ["eslint-config-airbnb", "prettier"],
      }));

      const result = analyzeConfig(dir, null);
      expect(result.eslint).not.toBeNull();
      expect(result.eslint!.config_file).toBe(".eslintrc.json");
      expect(result.eslint!.framework).toBe("airbnb");
    });

    it("returns null when no eslint config", () => {
      const dir = path.join(TMP_DIR, "no-eslint");
      fs.mkdirSync(dir, { recursive: true });

      const result = analyzeConfig(dir, null);
      expect(result.eslint).toBeNull();
    });
  });

  describe("prettier detection", () => {
    it("detects .prettierrc", () => {
      const dir = path.join(TMP_DIR, "prettier");
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, ".prettierrc"), "{}");

      const result = analyzeConfig(dir, null);
      expect(result.prettier).not.toBeNull();
      expect(result.prettier!.config_file).toBe(".prettierrc");
    });

    it("returns null when no prettier config", () => {
      const dir = path.join(TMP_DIR, "no-prettier");
      fs.mkdirSync(dir, { recursive: true });

      const result = analyzeConfig(dir, null);
      expect(result.prettier).toBeNull();
    });
  });
});
